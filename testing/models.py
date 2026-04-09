from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Test(models.Model):
    """Тест: набор вопросов; лимит времени опционален."""

    title = models.CharField("Название", max_length=255)
    description = models.TextField("Описание", blank=True)
    conduct_starts_at = models.DateTimeField(
        "Начало проведения",
        null=True,
        blank=True,
        help_text="Пусто — без ограничения с начала. До этой даты тест для сдающих недоступен.",
    )
    conduct_ends_at = models.DateTimeField(
        "Окончание проведения",
        null=True,
        blank=True,
        help_text="Пусто — без ограничения по окончанию. После этой даты тест недоступен; при сохранении флаг «Активен» снимается.",
    )
    time_limit_seconds = models.PositiveIntegerField(
        "Лимит времени (сек)",
        null=True,
        blank=True,
        help_text="Пусто — без ограничения. При истечении сохраняются уже данные ответы.",
    )
    is_active = models.BooleanField("Активен", default=True)
    allowed_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="allowed_tests",
        verbose_name="Отделы с доступом",
        help_text="Стандартные группы Django = отделы. Пусто — тест доступен любому авторизованному пользователю.",
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Тест"
        verbose_name_plural = "Тесты"
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return self.title

    def clean(self):
        if self.conduct_starts_at and self.conduct_ends_at:
            if self.conduct_starts_at >= self.conduct_ends_at:
                raise ValidationError(
                    {
                        "conduct_ends_at": "Дата окончания должна быть позже даты начала проведения."
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
        verbose_name="Тест",
    )
    text = models.TextField("Текст вопроса")
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    points = models.PositiveSmallIntegerField("Баллы за вопрос", default=1)

    class Meta:
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"
        ordering = ("test", "order", "id")

    def __str__(self) -> str:
        return f"{self.test.title}: {self.text[:50]}"


class AnswerOption(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="Вопрос",
    )
    text = models.CharField("Текст варианта", max_length=500)
    is_correct = models.BooleanField("Верный ответ", default=False)

    class Meta:
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответов"

    def __str__(self) -> str:
        return self.text[:60]


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "В процессе"
    COMPLETED = "completed", "Завершён"
    TIMED_OUT = "timed_out", "Истекло время"
    ABANDONED = "abandoned", "Прерван"


class TestAttempt(models.Model):
    """Одна попытка прохождения: время, статус, итоговые баллы (в т.ч. частичный результат)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="test_attempts",
        verbose_name="Пользователь",
    )
    test = models.ForeignKey(
        Test,
        on_delete=models.PROTECT,
        related_name="attempts",
        verbose_name="Тест",
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=AttemptStatus.choices,
        default=AttemptStatus.IN_PROGRESS,
        db_index=True,
    )
    started_at = models.DateTimeField("Начало", auto_now_add=True)
    finished_at = models.DateTimeField("Окончание", null=True, blank=True)
    deadline_at = models.DateTimeField(
        "Дедлайн",
        null=True,
        blank=True,
        help_text="Рассчитывается при старте, если у теста задан лимит времени.",
    )
    score_earned = models.DecimalField(
        "Набрано баллов",
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    score_max = models.DecimalField(
        "Максимум баллов (на момент расчёта)",
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    question_sequence = models.JSONField(
        "Порядок вопросов (id)",
        null=True,
        blank=True,
        help_text="Случайная перестановка при старте попытки; для next_question и согласованного порядка.",
    )

    class Meta:
        verbose_name = "Попытка"
        verbose_name_plural = "Попытки"
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
        verbose_name="Попытка",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        verbose_name="Вопрос",
    )
    selected_option = models.ForeignKey(
        AnswerOption,
        on_delete=models.CASCADE,
        verbose_name="Выбранный вариант",
    )
    is_correct = models.BooleanField("Верно", default=False)
    answered_at = models.DateTimeField("Отвечено", auto_now_add=True)

    class Meta:
        verbose_name = "Ответ в попытке"
        verbose_name_plural = "Ответы в попытке"
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

    PAGE_HIDDEN = "page_hidden", "Вкладка скрыта (visibility)"
    PAGE_VISIBLE = "page_visible", "Вкладка снова видна"
    WINDOW_BLUR = "window_blur", "Окно потеряло фокус"
    WINDOW_FOCUS = "window_focus", "Окно получило фокус"


class AttemptSessionEvent(models.Model):
    """Журнал ухода/возврата на вкладку и фокуса окна во время активной попытки."""

    attempt = models.ForeignKey(
        TestAttempt,
        on_delete=models.CASCADE,
        related_name="session_events",
        verbose_name="Попытка",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attempt_session_events",
        verbose_name="Пользователь",
    )
    event_type = models.CharField(
        "Тип события",
        max_length=32,
        choices=AttemptSessionEventType.choices,
        db_index=True,
    )
    created_at = models.DateTimeField("Записано на сервере", auto_now_add=True, db_index=True)
    client_timestamp = models.DateTimeField(
        "Время на клиенте",
        null=True,
        blank=True,
        help_text="ISO-время с браузера, если передано.",
    )
    duration_away_ms = models.PositiveIntegerField(
        "Длительность «вне вкладки», мс",
        null=True,
        blank=True,
        help_text="Обычно при page_visible: сколько мс вкладка была скрыта.",
    )
    leave_count = models.PositiveIntegerField(
        "Счётчик уходов (с клиента)",
        null=True,
        blank=True,
        help_text="Накопительный номер ухода, если фронт ведёт счётчик.",
    )
    meta = models.JSONField("Доп. данные", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("IP", null=True, blank=True)
    user_agent = models.CharField("User-Agent", max_length=512, blank=True)

    class Meta:
        verbose_name = "Событие сессии попытки"
        verbose_name_plural = "События сессий попыток"
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("attempt", "created_at")),
            models.Index(fields=("user", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id} {self.event_type} @ {self.created_at}"


class AdminActionType(models.TextChoices):
    CREATE = "create", "Создание"
    UPDATE = "update", "Изменение"
    DELETE = "delete", "Удаление"


class AdminActionLog(models.Model):
    """Отдельный журнал действий админов по объектам системы."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_action_logs",
        verbose_name="Кто выполнил",
    )
    action_type = models.CharField(
        "Тип действия",
        max_length=20,
        choices=AdminActionType.choices,
    )
    model_name = models.CharField("Модель", max_length=120, db_index=True)
    object_id = models.CharField("ID объекта", max_length=64, blank=True)
    object_repr = models.CharField("Объект", max_length=255, blank=True)
    changed_fields = models.JSONField("Изменённые поля", default=list, blank=True)
    ip_address = models.GenericIPAddressField("IP-адрес", null=True, blank=True)
    user_agent = models.TextField("User-Agent", blank=True)
    created_at = models.DateTimeField("Время", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Лог действий админа"
        verbose_name_plural = "Логи действий админа"
        ordering = ("-created_at",)

    def __str__(self):
        who = self.actor.username if self.actor else "unknown"
        return f"{who}: {self.get_action_type_display()} {self.model_name}#{self.object_id}"
