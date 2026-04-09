"""
Логика старта попытки, сохранения ответов и завершения по таймауту.
Частичный результат: каждый ответ пишется в БД сразу; при обрыве/таймауте
уже сохранённые ответы остаются, пересчитывается score_earned.
"""

from __future__ import annotations

import random

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    AnswerOption,
    AttemptResponse,
    AttemptStatus,
    Question,
    Test,
    TestAttempt,
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


def _close_timed_out(attempt: TestAttempt, now=None) -> None:
    now = now or timezone.now()
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return
    attempt.status = AttemptStatus.TIMED_OUT
    attempt.finished_at = min(now, attempt.deadline_at) if attempt.deadline_at else now
    _recalc_scores(attempt)
    attempt.save(update_fields=("status", "finished_at", "score_earned", "score_max"))


def _recalc_scores(attempt: TestAttempt) -> None:
    attempt.score_max = (
        attempt.test.questions.aggregate(total=Sum("points"))["total"] or 0
    )
    earned = (
        attempt.responses.filter(is_correct=True).aggregate(
            s=Sum("question__points")
        )["s"]
        or 0
    )
    attempt.score_earned = earned


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
        is_correct = selected_option.is_correct
        obj, _ = AttemptResponse.objects.update_or_create(
            attempt=attempt,
            question=question,
            defaults={
                "selected_option": selected_option,
                "is_correct": is_correct,
            },
        )
        _recalc_scores(attempt)
        total_questions = attempt.test.questions.count()
        answered_questions = attempt.responses.count()
        if total_questions > 0 and answered_questions >= total_questions:
            # Если пользователь ответил на все вопросы, закрываем попытку автоматически.
            attempt.status = AttemptStatus.COMPLETED
            attempt.finished_at = timezone.now()
            attempt.save(
                update_fields=(
                    "score_earned",
                    "score_max",
                    "status",
                    "finished_at",
                )
            )
        else:
            attempt.save(update_fields=("score_earned", "score_max"))
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
        attempt.status = AttemptStatus.COMPLETED
        attempt.finished_at = timezone.now()
        _recalc_scores(attempt)
        attempt.save(
            update_fields=("status", "finished_at", "score_earned", "score_max")
        )
        return attempt


def abandon_attempt(attempt: TestAttempt) -> TestAttempt:
    with transaction.atomic():
        attempt = TestAttempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return attempt
        attempt.status = AttemptStatus.ABANDONED
        attempt.finished_at = timezone.now()
        _recalc_scores(attempt)
        attempt.save(
            update_fields=("status", "finished_at", "score_earned", "score_max")
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
