from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .constants import REGION_MARKAZIY, REGION_VILOYAT, REGION_TYPE_CHOICES, VILOYAT_CHOICES


class Test(models.Model):
    title = models.CharField(_("Nomi"), max_length=255)
    description = models.TextField(_("Tavsifi"), blank=True)
    conduct_starts_at = models.DateTimeField(
        _("O'tkazish boshlanishi"),
        null=True,
        blank=True,
        help_text=_(
            "Bo'sh — boshidan cheklovsiz. Bu sanagacha test topshiruvchilarga mavjud emas."
        ),
    )
    conduct_ends_at = models.DateTimeField(
        _("O'tkazish tugashi"),
        null=True,
        blank=True,
        help_text=_(
            "Bo'sh — tugashida cheklovsiz. Bu sanadan keyin test mavjud emas; saqlashda «Faol» belgisi olib tashlanadi."
        ),
    )
    time_limit_seconds = models.PositiveIntegerField(
        _("Vaqt chegarasi (sek)"),
        null=True,
        blank=True,
        help_text=_(
            "Bo'sh — cheklovsiz. Vaqt tugaganda mavjud javoblar saqlanadi."
        ),
    )
    is_active = models.BooleanField(_("Faol"), default=True)
    allowed_groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="allowed_tests",
        verbose_name=_("Kirish huquqi bo'limlar"),
        help_text=_(
            "Django standart guruhlari = bo'limlar. Bo'sh — test har qanday autentifikatsiya qilingan foydalanuvchiga mavjud."
        ),
    )
    created_at = models.DateTimeField(_("Yaratilgan"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Yangilangan"), auto_now=True)

    class Meta:
        verbose_name = _("Test")
        verbose_name_plural = _("Testlar")
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return self.title

    def clean(self):
        if self.conduct_starts_at and self.conduct_ends_at:
            if self.conduct_starts_at >= self.conduct_ends_at:
                raise ValidationError(
                    {
                        "conduct_ends_at": _(
                            "Tugash sanasi boshlanish sanasidan keyin bo'lishi kerak."
                        )
                    }
                )

    def save(self, *args, **kwargs):
        now = timezone.now()
        if self.conduct_ends_at and now > self.conduct_ends_at:
            self.is_active = False
        super().save(*args, **kwargs)

    def is_conduct_period_open(self, now=None) -> bool:
        now = now or timezone.now()
        if self.conduct_starts_at is not None and now < self.conduct_starts_at:
            return False
        if self.conduct_ends_at is not None and now > self.conduct_ends_at:
            return False
        return True

    def total_points(self) -> int:
        return sum(q.points for q in self.questions.all()) or 0


class QuestionGroup(models.Model):
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="question_groups",
        verbose_name=_("Test"),
    )
    department = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_groups",
        verbose_name=_("Bo'lim"),
    )
    order = models.PositiveSmallIntegerField(_("Tartib"), default=0)
    questions_to_show = models.PositiveSmallIntegerField(
        _("Ko'rsatiladigan savollar soni"),
        null=True,
        blank=True,
        help_text=_(
            "Bo'sh — barcha savollar. Har bir urinishda tasodifiy tanlanadi."
        ),
    )

    class Meta:
        verbose_name = _("Savol guruhi")
        verbose_name_plural = _("Savol guruhlari")
        ordering = ("test", "order", "id")

    def __str__(self) -> str:
        dept = self.department.name if self.department_id else _("Guruh")
        return f"{self.test.title}: {dept}"


class Question(models.Model):
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name=_("Test"),
        null=True,
        blank=True,
    )
    group = models.ForeignKey(
        QuestionGroup,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name=_("Savol guruhi"),
        null=True,
        blank=True,
    )
    text = models.TextField(_("Savol matni"))
    order = models.PositiveSmallIntegerField(_("Tartib"), default=0)
    points = models.PositiveSmallIntegerField(_("Savol uchun ball"), default=1)

    class Meta:
        verbose_name = _("Savol")
        verbose_name_plural = _("Savollar")
        ordering = ("test", "order", "id")

    def __str__(self) -> str:
        return f"{self.test.title}: {self.text[:50]}" if self.test_id else self.text[:50]

    def save(self, *args, **kwargs):
        if self.group_id and not self.test_id:
            self.test_id = self.group.test_id
        super().save(*args, **kwargs)


class AnswerOption(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=_("Savol"),
    )
    text = models.CharField(_("Variant matni"), max_length=500)
    is_correct = models.BooleanField(_("To'g'ri javob"), default=False)

    class Meta:
        verbose_name = _("Javob varianti")
        verbose_name_plural = _("Javob variantlari")

    def __str__(self) -> str:
        return self.text[:60]


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", _("Jarayonda")
    COMPLETED = "completed", _("Yakunlangan")
    TIMED_OUT = "timed_out", _("Vaqt tugadi")
    ABANDONED = "abandoned", _("To'xtatilgan")
    TERMINATED = "terminated", _("Majburan tugatildi")


class TerminationReason(models.TextChoices):
    TAB_SWITCH = "tab_switch", _("Boshqa vkladkaga o'tildi")
    WINDOW_BLUR = "window_blur", _("Boshqa ilovaga o'tildi")


class TestAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="test_attempts",
        verbose_name=_("Foydalanuvchi"),
    )
    test = models.ForeignKey(
        Test,
        on_delete=models.PROTECT,
        related_name="attempts",
        verbose_name=_("Test"),
    )
    status = models.CharField(
        _("Holat"),
        max_length=20,
        choices=AttemptStatus.choices,
        default=AttemptStatus.IN_PROGRESS,
        db_index=True,
    )
    started_at = models.DateTimeField(_("Boshlanish"), auto_now_add=True)
    finished_at = models.DateTimeField(_("Tugash"), null=True, blank=True)
    deadline_at = models.DateTimeField(
        _("Muddat"),
        null=True,
        blank=True,
        help_text=_("Testda vaqt chegarasi belgilangan bo'lsa, startda hisoblanadi."),
    )
    score_earned = models.DecimalField(
        _("To'plangan ball"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    score_max = models.DecimalField(
        _("Maksimal ball (hisoblash vaqtida)"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    question_sequence = models.JSONField(
        _("Savollar tartibi (id)"),
        null=True,
        blank=True,
        help_text=_(
            "Urinish boshida tasodifiy tartib; next_question va muvofiq tartib uchun."
        ),
    )
    termination_reason = models.CharField(
        _("Tugatilish sababi"),
        max_length=20,
        choices=TerminationReason.choices,
        blank=True,
    )

    class Meta:
        verbose_name = _("Urinish")
        verbose_name_plural = _("Urinishlar")
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
    attempt = models.ForeignKey(
        TestAttempt,
        on_delete=models.CASCADE,
        related_name="responses",
        verbose_name=_("Urinish"),
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        verbose_name=_("Savol"),
    )
    selected_option = models.ForeignKey(
        AnswerOption,
        on_delete=models.CASCADE,
        verbose_name=_("Tanlangan variant"),
    )
    is_correct = models.BooleanField(_("To'g'ri"), default=False)
    answered_at = models.DateTimeField(_("Javob berilgan"), auto_now_add=True)

    class Meta:
        verbose_name = _("Urinishdagi javob")
        verbose_name_plural = _("Urinishdagi javoblar")
        constraints = [
            models.UniqueConstraint(
                fields=("attempt", "question"),
                name="unique_attempt_question_response",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id}: Q{self.question_id}"


class AttemptSessionEventType(models.TextChoices):
    PAGE_HIDDEN = "page_hidden", _("Sahifa yashirildi (visibility)")
    PAGE_VISIBLE = "page_visible", _("Sahifa yana ko'rinmoqda")
    WINDOW_BLUR = "window_blur", _("Oyna fokusni yo'qotdi")
    WINDOW_FOCUS = "window_focus", _("Oyna fokusni oldi")


class AttemptSessionEvent(models.Model):
    attempt = models.ForeignKey(
        TestAttempt,
        on_delete=models.CASCADE,
        related_name="session_events",
        verbose_name=_("Urinish"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attempt_session_events",
        verbose_name=_("Foydalanuvchi"),
    )
    event_type = models.CharField(
        _("Hodisa turi"),
        max_length=32,
        choices=AttemptSessionEventType.choices,
        db_index=True,
    )
    created_at = models.DateTimeField(
        _("Serverda qayd etilgan"), auto_now_add=True, db_index=True
    )
    client_timestamp = models.DateTimeField(
        _("Mijoz vaqti"),
        null=True,
        blank=True,
        help_text=_("Brauzerdan ISO vaqti, agar uzatilgan bo'lsa."),
    )
    duration_away_ms = models.PositiveIntegerField(
        _("Sahifadan tashqari davomiyligi, ms"),
        null=True,
        blank=True,
        help_text=_("Odatda page_visible da: sahifa necha ms yashiringan edi."),
    )
    leave_count = models.PositiveIntegerField(
        _("Ketish hisoblagichi (mijozdan)"),
        null=True,
        blank=True,
        help_text=_("To'planma ketish raqami, agar front hisoblagichni boshqarsa."),
    )
    meta = models.JSONField(_("Qo'shimcha ma'lumotlar"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("IP"), null=True, blank=True)
    user_agent = models.CharField(_("User-Agent"), max_length=512, blank=True)

    class Meta:
        verbose_name = _("Urinish sessiyasi hodisasi")
        verbose_name_plural = _("Urinish sessiyalari hodisalari")
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("attempt", "created_at")),
            models.Index(fields=("user", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id} {self.event_type} @ {self.created_at}"


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("Foydalanuvchi"),
    )
    region_type = models.CharField(
        _("Hudud turi"),
        max_length=20,
        choices=REGION_TYPE_CHOICES,
        default=REGION_MARKAZIY,
    )
    viloyat = models.CharField(
        _("Viloyat"),
        max_length=30,
        choices=VILOYAT_CHOICES,
        blank=True,
    )

    class Meta:
        verbose_name = _("Foydalanuvchi profili")
        verbose_name_plural = _("Foydalanuvchilar profillari")

    def __str__(self) -> str:
        return f"Profil: {self.user}"

    def clean(self):
        if self.region_type == REGION_VILOYAT and not self.viloyat:
            raise ValidationError({"viloyat": _("Viloyatni tanlang.")})
        if self.region_type != REGION_VILOYAT:
            self.viloyat = ""


class AdminActionType(models.TextChoices):
    CREATE = "create", _("Yaratish")
    UPDATE = "update", _("O'zgartirish")
    DELETE = "delete", _("O'chirish")


class AdminActionLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_action_logs",
        verbose_name=_("Kim bajardi"),
    )
    action_type = models.CharField(
        _("Harakat turi"),
        max_length=20,
        choices=AdminActionType.choices,
    )
    model_name = models.CharField(_("Model"), max_length=120, db_index=True)
    object_id = models.CharField(_("Obyekt ID"), max_length=64, blank=True)
    object_repr = models.CharField(_("Obyekt"), max_length=255, blank=True)
    changed_fields = models.JSONField(_("O'zgartirilgan maydonlar"), default=list, blank=True)
    ip_address = models.GenericIPAddressField(_("IP-manzil"), null=True, blank=True)
    user_agent = models.TextField(_("User-Agent"), blank=True)
    created_at = models.DateTimeField(_("Vaqt"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Admin harakatlari jurnali")
        verbose_name_plural = _("Admin harakatlari jurnallari")
        ordering = ("-created_at",)

    def __str__(self):
        who = self.actor.username if self.actor else "unknown"
        return f"{who}: {self.get_action_type_display()} {self.model_name}#{self.object_id}"
