from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Test(models.Model):
    """Тест: набор вопросов; лимит времени опционален."""

    title = models.CharField(_("Название"), max_length=255)
    description = models.TextField(_("Описание"), blank=True)
    conduct_starts_at = models.DateTimeField(
        _("Начало проведения"),
        null=True,
        blank=True,
        help_text=_(
            "Пусто — без ограничения с начала. До этой даты тест для сдающих недоступен."
        ),
    )
    conduct_ends_at = models.DateTimeField(
        _("Окончание проведения"),
        null=True,
        blank=True,
        help_text=_(
            "Пусто — без ограничения по окончанию. После этой даты тест недоступен; при сохранении флаг «Активен» снимается."
        ),
    )
    time_limit_seconds = models.PositiveIntegerField(
        _("Лимит времени (сек)"),
        null=True,
        blank=True,
        help_text=_(
            "Пусто — без ограничения. При истечении сохраняются уже данные ответы."
        ),
    )
    is_active = models.BooleanField(_("Активен"), default=True)
    allowed_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="allowed_tests",
        verbose_name=_("Отделы с доступом"),
        help_text=_(
            "Стандартные группы Django = отделы. Пусто — тест доступен любому авторизованному пользователю."
        ),
    )
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = _("Тест")
        verbose_name_plural = _("Тесты")
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return self.title

    def clean(self):
        if self.conduct_starts_at and self.conduct_ends_at:
            if self.conduct_starts_at >= self.conduct_ends_at:
                raise ValidationError(
                    {
                        "conduct_ends_at": _(
                            "Дата окончания должна быть позже даты начала проведения."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        now = timezone.now()
        if self.conduct_ends_at and now > self.conduct_ends_at:
            self.is_active = False
        super().save(*args, **kwargs)

    def is_conduct_period_open(self, now=None) -> bool:
        """Сейчас внутри окна проведения (пустые границы = без ограничения с этой стороны)."""
        now = now or timezone.now()
        if self.conduct_starts_at is not None and now < self.conduct_starts_at:
            return False
        if self.conduct_ends_at is not None and now > self.conduct_ends_at:
            return False
        return True

    def total_points(self) -> int:
        return sum(q.points for q in self.questions.all()) or 0


class Question(models.Model):
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name=_("Тест"),
    )
    text = models.TextField(_("Текст вопроса"))
    order = models.PositiveSmallIntegerField(_("Порядок"), default=0)
    points = models.PositiveSmallIntegerField(_("Баллы за вопрос"), default=1)

    class Meta:
        verbose_name = _("Вопрос")
        verbose_name_plural = _("Вопросы")
        ordering = ("test", "order", "id")

    def __str__(self) -> str:
        return f"{self.test.title}: {self.text[:50]}"


class AnswerOption(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=_("Вопрос"),
    )
    text = models.CharField(_("Текст варианта"), max_length=500)
    is_correct = models.BooleanField(_("Верный ответ"), default=False)

    class Meta:
        verbose_name = _("Вариант ответа")
        verbose_name_plural = _("Варианты ответов")

    def __str__(self) -> str:
        return self.text[:60]


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", _("В процессе")
    COMPLETED = "completed", _("Завершён")
    TIMED_OUT = "timed_out", _("Истекло время")
    ABANDONED = "abandoned", _("Прерван")


class TestAttempt(models.Model):
    """Одна попытка прохождения: время, статус, итоговые баллы (в т.ч. частичный результат)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="test_attempts",
        verbose_name=_("Пользователь"),
    )
    test = models.ForeignKey(
        Test,
        on_delete=models.PROTECT,
        related_name="attempts",
        verbose_name=_("Тест"),
    )
    status = models.CharField(
        _("Статус"),
        max_length=20,
        choices=AttemptStatus.choices,
        default=AttemptStatus.IN_PROGRESS,
        db_index=True,
    )
    started_at = models.DateTimeField(_("Начало"), auto_now_add=True)
    finished_at = models.DateTimeField(_("Окончание"), null=True, blank=True)
    deadline_at = models.DateTimeField(
        _("Дедлайн"),
        null=True,
        blank=True,
        help_text=_("Рассчитывается при старте, если у теста задан лимит времени."),
    )
    score_earned = models.DecimalField(
        _("Набрано баллов"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    score_max = models.DecimalField(
        _("Максимум баллов (на момент расчёта)"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    question_sequence = models.JSONField(
        _("Порядок вопросов (id)"),
        null=True,
        blank=True,
        help_text=_(
            "Случайная перестановка при старте попытки; для next_question и согласованного порядка."
        ),
    )

    class Meta:
        verbose_name = _("Попытка")
        verbose_name_plural = _("Попытки")
        ordering = ("-started_at",)
        indexes = [
            models.Index(fields=("-started_at",)),
            models.Index(fields=("user", "test")),
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.test} ({self.get_status_display()})"

    @property
    def duration_seconds(self):
        if not self.finished_at:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    def is_expired(self, now=None) -> bool:
        now = now or timezone.now()
        if self.deadline_at and now >= self.deadline_at:
            return True
        return False


class AttemptResponse(models.Model):
    """Ответ на один вопрос в рамках попытки (сохраняется сразу при отправке)."""

    attempt = models.ForeignKey(
        TestAttempt,
        on_delete=models.CASCADE,
        related_name="responses",
        verbose_name=_("Попытка"),
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        verbose_name=_("Вопрос"),
    )
    selected_option = models.ForeignKey(
        AnswerOption,
        on_delete=models.CASCADE,
        verbose_name=_("Выбранный вариант"),
    )
    is_correct = models.BooleanField(_("Верно"), default=False)
    answered_at = models.DateTimeField(_("Отвечено"), auto_now_add=True)

    class Meta:
        verbose_name = _("Ответ в попытке")
        verbose_name_plural = _("Ответы в попытке")
        constraints = [
            models.UniqueConstraint(
                fields=("attempt", "question"),
                name="unique_attempt_question_response",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id}: Q{self.question_id}"


class AttemptSessionEventType(models.TextChoices):
    """События с клиента при прохождении (visibility / focus)."""

    PAGE_HIDDEN = "page_hidden", _("Вкладка скрыта (visibility)")
    PAGE_VISIBLE = "page_visible", _("Вкладка снова видна")
    WINDOW_BLUR = "window_blur", _("Окно потеряло фокус")
    WINDOW_FOCUS = "window_focus", _("Окно получило фокус")


class AttemptSessionEvent(models.Model):
    """Журнал ухода/возврата на вкладку и фокуса окна во время активной попытки."""

    attempt = models.ForeignKey(
        TestAttempt,
        on_delete=models.CASCADE,
        related_name="session_events",
        verbose_name=_("Попытка"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attempt_session_events",
        verbose_name=_("Пользователь"),
    )
    event_type = models.CharField(
        _("Тип события"),
        max_length=32,
        choices=AttemptSessionEventType.choices,
        db_index=True,
    )
    created_at = models.DateTimeField(
        _("Записано на сервере"), auto_now_add=True, db_index=True
    )
    client_timestamp = models.DateTimeField(
        _("Время на клиенте"),
        null=True,
        blank=True,
        help_text=_("ISO-время с браузера, если передано."),
    )
    duration_away_ms = models.PositiveIntegerField(
        _("Длительность «вне вкладки», мс"),
        null=True,
        blank=True,
        help_text=_("Обычно при page_visible: сколько мс вкладка была скрыта."),
    )
    leave_count = models.PositiveIntegerField(
        _("Счётчик уходов (с клиента)"),
        null=True,
        blank=True,
        help_text=_("Накопительный номер ухода, если фронт ведёт счётчик."),
    )
    meta = models.JSONField(_("Доп. данные"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("IP"), null=True, blank=True)
    user_agent = models.CharField(_("User-Agent"), max_length=512, blank=True)

    class Meta:
        verbose_name = _("Событие сессии попытки")
        verbose_name_plural = _("События сессий попыток")
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("attempt", "created_at")),
            models.Index(fields=("user", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id} {self.event_type} @ {self.created_at}"


class AdminActionType(models.TextChoices):
    CREATE = "create", _("Создание")
    UPDATE = "update", _("Изменение")
    DELETE = "delete", _("Удаление")


class AdminActionLog(models.Model):
    """Отдельный журнал действий админов по объектам системы."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_action_logs",
        verbose_name=_("Кто выполнил"),
    )
    action_type = models.CharField(
        _("Тип действия"),
        max_length=20,
        choices=AdminActionType.choices,
    )
    model_name = models.CharField(_("Модель"), max_length=120, db_index=True)
    object_id = models.CharField(_("ID объекта"), max_length=64, blank=True)
    object_repr = models.CharField(_("Объект"), max_length=255, blank=True)
    changed_fields = models.JSONField(_("Изменённые поля"), default=list, blank=True)
    ip_address = models.GenericIPAddressField(_("IP-адрес"), null=True, blank=True)
    user_agent = models.TextField(_("User-Agent"), blank=True)
    created_at = models.DateTimeField(_("Время"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Лог действий админа")
        verbose_name_plural = _("Логи действий админа")
        ordering = ("-created_at",)

    def __str__(self):
        who = self.actor.username if self.actor else "unknown"
        return f"{who}: {self.get_action_type_display()} {self.model_name}#{self.object_id}"
