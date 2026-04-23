"""
Логика старта попытки, сохранения ответов и завершения по таймауту.
Частичный результат: каждый ответ пишется в БД сразу; при обрыве/таймауте
уже сохранённые ответы остаются, пересчитывается score_earned.
"""

from __future__ import annotations

import random

from django.db import transaction
from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    AnswerOption,
    AttemptResponse,
    AttemptStatus,
    Question,
    Test,
    TestAttempt,
    TerminationReason,
)


class AttemptError(Exception):
    """Бизнес-ошибка (нельзя ответить, попытка закрыта и т.д.)."""


def user_can_access_test(user, test: Test) -> bool:
    if not test.is_active:
        return False
    if not test.is_conduct_period_open():
        return False
    groups = test.allowed_groups.all()
    if not groups.exists():
        return True
    return test.allowed_groups.filter(pk__in=user.groups.values_list("pk", flat=True)).exists()


def user_has_finished_attempt_for_test(user, test: Test) -> bool:
    """Есть ли у пользователя завершённая попытка по этому тесту (не «в процессе»)."""
    return TestAttempt.objects.filter(user=user, test=test).exclude(
        status=AttemptStatus.IN_PROGRESS
    ).exists()


def start_attempt(user, test: Test) -> TestAttempt:
    if not getattr(user, "is_staff", False) and not user_can_access_test(user, test):
        raise AttemptError("Нет доступа к этому тесту.")
    if user_has_finished_attempt_for_test(user, test):
        raise AttemptError(
            "Этот тест можно пройти только один раз. Повторное прохождение недоступно."
        )
    now = timezone.now()
    deadline = None
    if test.time_limit_seconds:
        deadline = now + timezone.timedelta(seconds=test.time_limit_seconds)
    max_pts = (
        test.questions.aggregate(total=Sum("points"))["total"] or 0
    )
    q_ids = list(
        test.questions.order_by("order", "id").values_list("pk", flat=True)
    )
    random.shuffle(q_ids)
    return TestAttempt.objects.create(
        user=user,
        test=test,
        status=AttemptStatus.IN_PROGRESS,
        deadline_at=deadline,
        score_max=max_pts,
        question_sequence=q_ids,
    )


def _ensure_in_progress(attempt: TestAttempt) -> None:
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise AttemptError("Попытка уже завершена.")
    if attempt.is_expired():
        _close_timed_out(attempt)
        raise AttemptError("Время вышло; сохранены ответы, отправленные до дедлайна.")


# Тип поля для score_earned / score_max
_SCORE_FIELD = DecimalField(max_digits=10, decimal_places=2)


def _earned_subquery() -> Coalesce:
    """Сумма баллов за правильные ответы — коррелированный подзапрос."""
    return Coalesce(
        Subquery(
            AttemptResponse.objects
            .filter(attempt_id=OuterRef("pk"), is_correct=True)
            .values("attempt_id")
            .annotate(s=Sum("question__points"))
            .values("s")[:1],
            output_field=_SCORE_FIELD,
        ),
        Value(0, output_field=_SCORE_FIELD),
    )


def _max_subquery() -> Coalesce:
    """Максимальный балл за тест — коррелированный подзапрос."""
    return Coalesce(
        Subquery(
            Question.objects
            .filter(test_id=OuterRef("test_id"))
            .values("test_id")
            .annotate(s=Sum("points"))
            .values("s")[:1],
            output_field=_SCORE_FIELD,
        ),
        Value(0, output_field=_SCORE_FIELD),
    )


def _save_scores_atomically(
    attempt: TestAttempt,
    extra_fields: dict | None = None,
) -> None:
    """
    Пересчитывает score_earned / score_max и сохраняет их одним UPDATE-запросом.

    Устраняет race condition: вместо read-modify-write на стороне Python
    выполняется одна атомарная операция на уровне БД. Никакой другой транзакции
    не виден «старый» score между чтением и записью.
    """
    updates: dict = {
        "score_earned": _earned_subquery(),
        "score_max": _max_subquery(),
        **(extra_fields or {}),
    }
    TestAttempt.objects.filter(pk=attempt.pk).update(**updates)
    refresh = ["score_earned", "score_max"] + [
        k for k in (extra_fields or {}) if k not in ("score_earned", "score_max")
    ]
    attempt.refresh_from_db(fields=refresh)


def _close_timed_out(attempt: TestAttempt, now=None) -> None:
    now = now or timezone.now()
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return
    _save_scores_atomically(attempt, {
        "status": AttemptStatus.TIMED_OUT,
        "finished_at": min(now, attempt.deadline_at) if attempt.deadline_at else now,
    })


def submit_answer(
    attempt: TestAttempt,
    question: Question,
    selected_option: AnswerOption,
) -> AttemptResponse:
    """Сохранить/обновить ответ на вопрос (upsert по паре попытка+вопрос)."""
    with transaction.atomic():
        attempt = TestAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.is_expired():
            _close_timed_out(attempt)
            raise AttemptError("Время истекло.")
        _ensure_in_progress(attempt)
        if question.test_id != attempt.test_id:
            raise AttemptError("Вопрос не из этого теста.")
        if selected_option.question_id != question.id:
            raise AttemptError("Вариант не относится к вопросу.")
        obj, _ = AttemptResponse.objects.update_or_create(
            attempt=attempt,
            question=question,
            defaults={
                "selected_option": selected_option,
                "is_correct": selected_option.is_correct,
            },
        )
        total_questions = attempt.test.questions.count()
        answered_questions = attempt.responses.count()
        is_complete = total_questions > 0 and answered_questions >= total_questions
        _save_scores_atomically(
            attempt,
            {"status": AttemptStatus.COMPLETED, "finished_at": timezone.now()}
            if is_complete else None,
        )
        return obj


def complete_attempt(attempt: TestAttempt) -> TestAttempt:
    """Нормальное завершение (все вопросы или пользователь нажал «готово»)."""
    with transaction.atomic():
        attempt = TestAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return attempt
        if attempt.is_expired():
            _close_timed_out(attempt)
            return attempt
        _save_scores_atomically(attempt, {
            "status": AttemptStatus.COMPLETED,
            "finished_at": timezone.now(),
        })
        return attempt


def abandon_attempt(attempt: TestAttempt) -> TestAttempt:
    with transaction.atomic():
        attempt = TestAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return attempt
        _save_scores_atomically(attempt, {
            "status": AttemptStatus.ABANDONED,
            "finished_at": timezone.now(),
        })
        return attempt


def terminate_attempt(attempt: TestAttempt, reason: str) -> TestAttempt:
    """Принудительное закрытие (смена вкладки/приложения): score_earned = 0."""
    with transaction.atomic():
        attempt = TestAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return attempt
        # Не пересчитываем score_earned — при нарушении он обнуляется.
        TestAttempt.objects.filter(pk=attempt.pk).update(
            status=AttemptStatus.TERMINATED,
            finished_at=timezone.now(),
            termination_reason=reason,
            score_earned=Value(0, output_field=_SCORE_FIELD),
            score_max=_max_subquery(),
        )
        attempt.refresh_from_db(
            fields=["status", "finished_at", "termination_reason", "score_earned", "score_max"]
        )
        return attempt


def sync_expired_attempt(attempt: TestAttempt) -> TestAttempt:
    """Если дедлайн прошёл, закрыть попытку (для фоновых задач / перед ответом)."""
    with transaction.atomic():
        attempt = TestAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.status == AttemptStatus.IN_PROGRESS and attempt.is_expired():
            _close_timed_out(attempt)
        return attempt


def get_request_client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR")
