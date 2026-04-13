import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

import nested_admin
from django.contrib import admin
from django.db.models import Count, Q
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .constants import TEST_CURATOR_GROUP
from .models import (
    AdminActionLog,
    AdminActionType,
    AnswerOption,
    AttemptResponse,
    AttemptSessionEvent,
    AttemptSessionEventType,
    Question,
    Test,
    TestAttempt,
)
from .services import sync_expired_attempt

User = get_user_model()
AUDIT_LOG_VIEWERS_GROUP = "Просмотр логов админов"


def _is_test_curator(request) -> bool:
    u = request.user
    return (
        u.is_authenticated
        and not u.is_superuser
        and u.groups.filter(name=TEST_CURATOR_GROUP).exists()
    )


def _get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AdminActionLoggingMixin:
    """Унифицированное логирование create/update/delete из админки."""

    def _write_admin_log(self, request, obj, action_type, changed_fields=None):
        AdminActionLog.objects.create(
            actor=request.user if request.user.is_authenticated else None,
            action_type=action_type,
            model_name=obj._meta.label,
            object_id=str(getattr(obj, "pk", "")),
            object_repr=str(obj)[:255],
            changed_fields=changed_fields or [],
            ip_address=_get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        action = AdminActionType.UPDATE if change else AdminActionType.CREATE
        self._write_admin_log(request, obj, action, getattr(form, "changed_data", []))

    def delete_model(self, request, obj):
        self._write_admin_log(request, obj, AdminActionType.DELETE, [])
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # В админке "Удалить выбранные" вызывает именно этот метод.
        for obj in queryset:
            self._write_admin_log(request, obj, AdminActionType.DELETE, [])
        super().delete_queryset(request, queryset)


class RequiredDepartmentUserCreationForm(UserCreationForm):
    def clean_groups(self):
        groups = self.cleaned_data.get("groups")
        if not groups or groups.count() == 0:
            raise ValidationError(_("Нужно выбрать хотя бы один отдел."))
        return groups


class RequiredDepartmentUserChangeForm(UserChangeForm):
    def clean_groups(self):
        groups = self.cleaned_data.get("groups")
        if not groups or groups.count() == 0:
            raise ValidationError(_("Нужно выбрать хотя бы один отдел."))
        return groups


class UserAdmin(AdminActionLoggingMixin, BaseUserAdmin):
    """Пользователь обязательно должен быть привязан минимум к одному отделу."""

    form = RequiredDepartmentUserChangeForm
    add_form = RequiredDepartmentUserCreationForm
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2", "groups"),
            },
        ),
    )

    _curator_add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "email",
                    "groups",
                ),
            },
        ),
    )

    _curator_change_fieldsets = (
        (None, {"fields": ("username",)}),
        (_("Пароль"), {"fields": ("password",)}),
        (_("Личная информация"), {"fields": ("first_name", "last_name", "email")}),
        (_("Отделы"), {"fields": ("groups",)}),
    )

    def get_fieldsets(self, request, obj=None):
        if _is_test_curator(request):
            if obj is None:
                return self._curator_add_fieldsets
            return self._curator_change_fieldsets
        return super().get_fieldsets(request, obj)

    def save_model(self, request, obj, form, change):
        # Новые пользователи куратором — только обычные (не staff / не суперпользователь).
        if _is_test_curator(request) and not change:
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)


if admin.site.is_registered(User):
    admin.site.unregister(User)
admin.site.register(User, UserAdmin)


class AnswerOptionInlineFormSet(BaseInlineFormSet):
    """Не даём сохранить вопрос без отмеченного верного варианта."""

    def clean(self):
        super().clean()
        correct_count = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE", False):
                continue
            if form.cleaned_data.get("is_correct"):
                correct_count += 1
        if correct_count < 1:
            raise ValidationError(
                _(
                    "Для каждого вопроса нужно отметить минимум один верный вариант ответа."
                )
            )


class AnswerOptionNestedInline(nested_admin.NestedTabularInline):
    """Ровно 4 варианта на вопрос при создании/редактировании теста."""

    model = AnswerOption
    extra = 4
    min_num = 4
    max_num = 4
    fields = ("text", "is_correct")
    formset = AnswerOptionInlineFormSet


class QuestionNestedInline(nested_admin.NestedStackedInline):
    model = Question
    extra = 1
    fields = ("order", "text", "points")
    inlines = (AnswerOptionNestedInline,)


@admin.register(Test)
class TestAdmin(AdminActionLoggingMixin, nested_admin.NestedModelAdmin):
    list_display = (
        "title",
        "is_active",
        "conduct_schedule_display",
        "time_limit_seconds",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("title", "description")
    filter_horizontal = ("allowed_groups",)
    inlines = (QuestionNestedInline,)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("title", "description", "is_active")}),
        (
            _("Период проведения"),
            {
                "fields": ("conduct_starts_at", "conduct_ends_at"),
                "description": _(
                    "Вне этого интервала тест для сдающих недоступен. После окончания при сохранении снимается «Активен»."
                ),
            },
        ),
        (_("Параметры"), {"fields": ("time_limit_seconds", "allowed_groups")}),
        (_("Служебное"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description=_("Период проведения"))
    def conduct_schedule_display(self, obj: Test):
        from django.utils.formats import date_format

        s, e = obj.conduct_starts_at, obj.conduct_ends_at
        if not s and not e:
            return _("без срока")

        def fmt(dt):
            return date_format(dt, "SHORT_DATETIME_FORMAT") if dt else _("—")

        return f"{fmt(s)} — {fmt(e)}"


class AttemptResponseInline(admin.TabularInline):
    model = AttemptResponse
    extra = 0
    readonly_fields = ("is_correct", "answered_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("question", "selected_option")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "question":
            obj_id = request.resolver_match.kwargs.get("object_id")
            if obj_id:
                try:
                    att = TestAttempt.objects.get(pk=obj_id)
                    kwargs["queryset"] = Question.objects.filter(test=att.test)
                except TestAttempt.DoesNotExist:
                    pass
        if db_field.name == "selected_option":
            obj_id = request.resolver_match.kwargs.get("object_id")
            if obj_id:
                try:
                    att = TestAttempt.objects.get(pk=obj_id)
                    kwargs["queryset"] = AnswerOption.objects.filter(
                        question__test=att.test
                    )
                except TestAttempt.DoesNotExist:
                    pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class AttemptSessionEventInline(admin.TabularInline):
    """Журнал visibility/focus на карточке попытки (только просмотр)."""

    model = AttemptSessionEvent
    extra = 0
    can_delete = False
    max_num = 0
    fields = (
        "event_type",
        "created_at",
        "client_timestamp",
        "leave_count",
        "duration_away_ms",
        "ip_address",
    )
    readonly_fields = fields
    ordering = ("created_at",)

    def has_add_permission(self, request, obj=None):
        return False


def _fmt_duration(seconds):
    """Конвертировать секунды в строку М:СС или Ч:ММ:СС."""
    if seconds is None:
        return "—"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


@admin.action(description=_("Экспорт выбранных попыток в Excel"))
def export_attempts_xlsx(modeladmin, request, queryset):
    qs = (
        queryset
        .select_related("user", "test")
        .prefetch_related("user__groups")
        .annotate(
            _tab_hidden=Count(
                "session_events",
                filter=Q(session_events__event_type=AttemptSessionEventType.PAGE_HIDDEN),
            ),
            _window_blur=Count(
                "session_events",
                filter=Q(session_events__event_type=AttemptSessionEventType.WINDOW_BLUR),
            ),
            _answered=Count("responses"),
        )
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Попытки"

    headers = [
        "ID",
        "ФИО",
        "Логин",
        "Отдел",
        "Тест",
        "Статус",
        "Начало",
        "Конец",
        "Длительность",
        "Набрано",
        "Максимум",
        "Результат (%)",
        "Отвечено вопросов",
        "Уходы со вкладки",
        "Уходы из окна",
    ]

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(fill_type="solid", fgColor="2563EB")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32

    fmt_dt = "%d.%m.%Y %H:%M"

    for obj in qs:
        department = obj.user.groups.first()
        pct = (
            round(float(obj.score_earned / obj.score_max * 100), 1)
            if obj.score_max
            else "—"
        )
        ws.append([
            obj.pk,
            obj.user.get_full_name() or obj.user.username,
            obj.user.username,
            department.name if department else "—",
            str(obj.test),
            obj.get_status_display(),
            obj.started_at.strftime(fmt_dt) if obj.started_at else "—",
            obj.finished_at.strftime(fmt_dt) if obj.finished_at else "—",
            _fmt_duration(obj.duration_seconds),
            float(obj.score_earned),
            float(obj.score_max),
            pct,
            obj._answered,
            obj._tab_hidden,
            obj._window_blur,
        ])

    col_widths = [6, 28, 18, 20, 32, 16, 18, 18, 14, 10, 10, 14, 18, 16, 16]
    for col_idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="attempts.xlsx"'
    wb.save(response)
    return response


@admin.register(TestAttempt)
class TestAttemptAdmin(AdminActionLoggingMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "test",
        "status",
        "tab_hidden_events_display",
        "window_blur_events_display",
        "started_at",
        "finished_at",
        "duration_display",
        "score_display",
        "answered_count",
    )
    list_filter = (
        "status",
        "test",
        "user__groups",
        "started_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "test__title",
    )
    date_hierarchy = "started_at"
    readonly_fields = (
        "started_at",
        "deadline_at",
        "finished_at",
        "duration_display",
        "score_earned",
        "score_max",
    )
    autocomplete_fields = ("user", "test")
    inlines = (AttemptResponseInline, AttemptSessionEventInline)
    actions = ("action_sync_timeout", export_attempts_xlsx)

    def get_inline_instances(self, request, obj=None):
        inlines = super().get_inline_instances(request, obj)
        if request.user.is_superuser:
            return inlines
        if not request.user.has_perm("testing.change_attemptresponse"):
            inlines = [
                i
                for i in inlines
                if not isinstance(i, AttemptResponseInline)
            ]
        if not request.user.has_perm("testing.change_attemptsessionevent"):
            inlines = [
                i
                for i in inlines
                if not isinstance(i, AttemptSessionEventInline)
            ]
        return inlines

    @admin.display(description=_("Длительность"))
    def duration_display(self, obj: TestAttempt):
        sec = obj.duration_seconds
        if sec is None:
            return _("—")
        if sec < 60:
            return _("{n} с").format(n=int(sec))
        m, s = divmod(int(sec), 60)
        return _("{m} мин {s} с").format(m=m, s=s)

    @admin.display(description=_("Баллы"))
    def score_display(self, obj: TestAttempt):
        if obj.score_max and obj.score_max > 0:
            pct = (obj.score_earned / obj.score_max) * 100
            # format_html экранирует аргументы в SafeString — нельзя использовать {:.0f} в шаблоне.
            pct_label = str(int(round(float(pct))))
            return format_html(
                "{} / {} (<span>{}%</span>)",
                obj.score_earned,
                obj.score_max,
                pct_label,
            )
        return f"{obj.score_earned} / {obj.score_max}"

    @admin.display(description=_("Отвечено вопросов"))
    def answered_count(self, obj: TestAttempt):
        return obj.responses.count()

    @admin.display(
        description=_("Вкладка скрыта"),
        ordering="_tab_hidden_count",
    )
    def tab_hidden_events_display(self, obj: TestAttempt):
        n = getattr(obj, "_tab_hidden_count", None)
        if n is None:
            n = obj.session_events.filter(
                event_type=AttemptSessionEventType.PAGE_HIDDEN
            ).count()
        if n == 0:
            return format_html('<span style="color:#9ca3af">—</span>')
        return format_html(
            '<span style="color:#b45309;font-weight:600" title="{}">⚠ {}</span>',
            _("Зафиксировано событий «Вкладка скрыта» (visibility)"),
            n,
        )

    @admin.display(
        description=_("Окно без фокуса"),
        ordering="_window_blur_count",
    )
    def window_blur_events_display(self, obj: TestAttempt):
        n = getattr(obj, "_window_blur_count", None)
        if n is None:
            n = obj.session_events.filter(
                event_type=AttemptSessionEventType.WINDOW_BLUR
            ).count()
        if n == 0:
            return format_html('<span style="color:#9ca3af">—</span>')
        return format_html(
            '<span style="color:#7c3aed;font-weight:600" title="{}">◆ {}</span>',
            _("Зафиксировано событий «Окно потеряло фокус»"),
            n,
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("user", "test").prefetch_related(
            "user__groups",
            "responses",
        )
        qs = qs.annotate(
            _tab_hidden_count=Count(
                "session_events",
                filter=Q(
                    session_events__event_type=AttemptSessionEventType.PAGE_HIDDEN
                ),
            ),
            _window_blur_count=Count(
                "session_events",
                filter=Q(
                    session_events__event_type=AttemptSessionEventType.WINDOW_BLUR
                ),
            ),
        )
        return qs

    @admin.action(
        description=_("Обновить статус по истечении времени (таймаут)"),
    )
    def action_sync_timeout(self, request, queryset):
        for att in queryset:
            sync_expired_attempt(att)


@admin.register(AttemptSessionEvent)
class AttemptSessionEventAdmin(admin.ModelAdmin):
    """Журнал уходов с вкладки / фокуса во время попытки (только чтение)."""

    list_display = (
        "id",
        "attempt",
        "user",
        "event_type",
        "created_at",
        "client_timestamp",
        "leave_count",
        "duration_away_ms",
        "ip_address",
    )
    list_filter = ("event_type", "created_at")
    search_fields = ("user__username", "user__email")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = (
        "attempt",
        "user",
        "event_type",
        "created_at",
        "client_timestamp",
        "duration_away_ms",
        "leave_count",
        "meta",
        "ip_address",
        "user_agent",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AttemptResponse)
class AttemptResponseAdmin(AdminActionLoggingMixin, admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct", "answered_at")
    list_filter = ("is_correct", "attempt__test")
    search_fields = ("attempt__user__username", "question__text")
    readonly_fields = ("answered_at",)


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    """Просмотр журнала доступен только отдельной роли."""

    list_display = (
        "created_at",
        "actor",
        "action_type",
        "model_name",
        "object_id",
        "object_repr",
    )
    list_filter = ("action_type", "model_name", "created_at")
    search_fields = ("actor__username", "model_name", "object_id", "object_repr")
    date_hierarchy = "created_at"
    readonly_fields = (
        "actor",
        "action_type",
        "model_name",
        "object_id",
        "object_repr",
        "changed_fields",
        "ip_address",
        "user_agent",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _can_view(self, request):
        user = request.user
        if not (user and user.is_active and user.is_staff):
            return False
        if user.is_superuser:
            return True
        return bool(
            user.groups.filter(name=AUDIT_LOG_VIEWERS_GROUP).exists()
            or user.has_perm("testing.view_adminactionlog")
        )

    def has_module_permission(self, request):
        return self._can_view(request)

    def has_view_permission(self, request, obj=None):
        return self._can_view(request)
