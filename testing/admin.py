import nested_admin
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.html import format_html

from .models import (
    AdminActionLog,
    AdminActionType,
    AnswerOption,
    AttemptResponse,
    AttemptSessionEvent,
    Question,
    Test,
    TestAttempt,
)
from .services import sync_expired_attempt

User = get_user_model()
AUDIT_LOG_VIEWERS_GROUP = "Просмотр логов админов"


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
            raise ValidationError("Нужно выбрать хотя бы один отдел.")
        return groups


class RequiredDepartmentUserChangeForm(UserChangeForm):
    def clean_groups(self):
        groups = self.cleaned_data.get("groups")
        if not groups or groups.count() == 0:
            raise ValidationError("Нужно выбрать хотя бы один отдел.")
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
                "Для каждого вопроса нужно отметить минимум один верный вариант ответа."
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
            "Период проведения",
            {
                "fields": ("conduct_starts_at", "conduct_ends_at"),
                "description": "Вне этого интервала тест для сдающих недоступен. После окончания при сохранении снимается «Активен».",
            },
        ),
        ("Параметры", {"fields": ("time_limit_seconds", "allowed_groups")}),
        ("Служебное", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Период проведения")
    def conduct_schedule_display(self, obj: Test):
        from django.utils.formats import date_format

        s, e = obj.conduct_starts_at, obj.conduct_ends_at
        if not s and not e:
            return "без срока"

        def fmt(dt):
            return date_format(dt, "SHORT_DATETIME_FORMAT") if dt else "—"

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


@admin.register(TestAttempt)
class TestAttemptAdmin(AdminActionLoggingMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "test",
        "status",
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
    inlines = (AttemptResponseInline,)
    actions = ("action_sync_timeout",)

    @admin.display(description="Длительность")
    def duration_display(self, obj: TestAttempt):
        sec = obj.duration_seconds
        if sec is None:
            return "—"
        if sec < 60:
            return f"{int(sec)} с"
        m, s = divmod(int(sec), 60)
        return f"{m} мин {s} с"

    @admin.display(description="Баллы")
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

    @admin.display(description="Отвечено вопросов")
    def answered_count(self, obj: TestAttempt):
        return obj.responses.count()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user", "test").prefetch_related(
            "user__groups",
            "responses",
        )

    @admin.action(description="Обновить статус по истечении времени (таймаут)")
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
