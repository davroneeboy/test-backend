import random

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import (
    AnswerOption,
    AttemptResponse,
    AttemptSessionEvent,
    AttemptStatus,
    Question,
    Test,
    TestAttempt,
)

User = get_user_model()


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ("id", "name")


class UserProfileSerializer(serializers.ModelSerializer):
    """Профиль для UI: отделы + ФИО для шапки (вместо одного логина)."""

    departments = DepartmentSerializer(source="groups", many=True, read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "is_staff",
            "departments",
        )
        read_only_fields = (
            "id",
            "username",
            "is_staff",
            "departments",
            "full_name",
        )

    def get_full_name(self, obj):
        name = obj.get_full_name().strip()
        return name if name else obj.username


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")

    def validate_email(self, value):
        value = (value or "").strip()
        if not value:
            return ""
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Пользователь с таким email уже есть.")
        return value


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Неверный текущий пароль.")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value


class ExamOptionSerializer(serializers.ModelSerializer):
    """Варианты без признака верности — для прохождения теста."""

    class Meta:
        model = AnswerOption
        fields = ("id", "text")


class ExamQuestionSerializer(serializers.ModelSerializer):
    options = ExamOptionSerializer(many=True, read_only=True)
    correct_options_count = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = (
            "id",
            "text",
            "order",
            "points",
            "correct_options_count",
            "options",
        )

    def get_correct_options_count(self, obj):
        """Сколько вариантов помечены верными (без раскрытия, какие именно)."""
        return sum(1 for o in obj.options.all() if o.is_correct)


class TestListSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(read_only=True)
    conduct_period_open = serializers.SerializerMethodField()

    class Meta:
        model = Test
        fields = (
            "id",
            "title",
            "description",
            "conduct_starts_at",
            "conduct_ends_at",
            "conduct_period_open",
            "time_limit_seconds",
            "is_active",
            "question_count",
            "updated_at",
        )

    def get_conduct_period_open(self, obj):
        return obj.is_conduct_period_open()


class TestDetailSerializer(serializers.ModelSerializer):
    questions = ExamQuestionSerializer(many=True, read_only=True)
    conduct_period_open = serializers.SerializerMethodField()

    class Meta:
        model = Test
        fields = (
            "id",
            "title",
            "description",
            "conduct_starts_at",
            "conduct_ends_at",
            "conduct_period_open",
            "time_limit_seconds",
            "is_active",
            "questions",
            "updated_at",
        )

    def get_conduct_period_open(self, obj):
        return obj.is_conduct_period_open()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        questions = data.get("questions")
        if questions:
            request = self.context.get("request")
            user_pk = request.user.pk if request and request.user.is_authenticated else 0
            rng = random.Random(user_pk * 10 ** 6 + instance.pk)
            rng.shuffle(questions)
            for q in questions:
                opts = q.get("options")
                if opts:
                    rng.shuffle(opts)
        return data


class AttemptResponseSerializer(serializers.ModelSerializer):
    question_id = serializers.IntegerField(source="question.id", read_only=True)
    selected_option_id = serializers.IntegerField(
        source="selected_option.id", read_only=True
    )
    is_correct = serializers.SerializerMethodField()

    class Meta:
        model = AttemptResponse
        fields = (
            "question_id",
            "selected_option_id",
            "is_correct",
            "answered_at",
        )

    def get_is_correct(self, obj):
        attempt = self.context.get("attempt")
        request = self.context.get("request")
        if not attempt or not request:
            return None
        if attempt.status == AttemptStatus.IN_PROGRESS:
            return None
        return obj.is_correct


class AttemptSessionEventReadSerializer(serializers.ModelSerializer):
    """События visibility/focus в ответе по попытке."""

    class Meta:
        model = AttemptSessionEvent
        fields = (
            "id",
            "event_type",
            "created_at",
            "client_timestamp",
            "duration_away_ms",
            "leave_count",
            "meta",
        )


class AttemptSerializer(serializers.ModelSerializer):
    test_id = serializers.IntegerField(source="test.id", read_only=True)
    test_title = serializers.CharField(source="test.title", read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    seconds_remaining = serializers.SerializerMethodField()
    server_time = serializers.SerializerMethodField()
    responses = serializers.SerializerMethodField()
    questions_total = serializers.SerializerMethodField()
    questions_answered = serializers.SerializerMethodField()
    answered_question_ids = serializers.SerializerMethodField()
    next_question = serializers.SerializerMethodField()
    session_events = serializers.SerializerMethodField()

    class Meta:
        model = TestAttempt
        fields = (
            "id",
            "test_id",
            "test_title",
            "status",
            "started_at",
            "finished_at",
            "deadline_at",
            "server_time",
            "seconds_remaining",
            "score_earned",
            "score_max",
            "duration_seconds",
            "responses",
            "questions_total",
            "questions_answered",
            "answered_question_ids",
            "next_question",
            "session_events",
        )

    def get_duration_seconds(self, obj):
        v = obj.duration_seconds
        return float(v) if v is not None else None

    def get_seconds_remaining(self, obj):
        from django.utils import timezone

        if obj.status != AttemptStatus.IN_PROGRESS or not obj.deadline_at:
            return None
        delta = obj.deadline_at - timezone.now()
        sec = int(delta.total_seconds())
        return max(0, sec)

    def get_server_time(self, obj):
        from django.utils import timezone

        return timezone.now()

    def get_responses(self, obj):
        responses = sorted(obj.responses.all(), key=lambda r: r.answered_at)
        return AttemptResponseSerializer(
            responses,
            many=True,
            context={**self.context, "attempt": obj},
        ).data

    def get_session_events(self, obj):
        cache = getattr(obj, "_prefetched_objects_cache", None)
        if cache and "session_events" in cache:
            events = list(cache["session_events"])
            events.sort(key=lambda e: e.created_at)
        else:
            events = list(obj.session_events.order_by("created_at"))
        return AttemptSessionEventReadSerializer(events, many=True).data

    def _answered_map(self, obj):
        return {
            r.question_id: r.selected_option_id
            for r in obj.responses.all()
        }

    def get_questions_total(self, obj):
        return len(obj.test.questions.all())

    def get_questions_answered(self, obj):
        return len(obj.responses.all())

    def get_answered_question_ids(self, obj):
        return sorted(self._answered_map(obj).keys())

    def get_next_question(self, obj):
        if obj.status != AttemptStatus.IN_PROGRESS:
            return None
        answered = self._answered_map(obj)
        qs = obj.test.questions.prefetch_related("options")

        def build_payload(question):
            opts = list(question.options.all())
            rng = random.Random(f"{obj.pk}:{question.id}")
            rng.shuffle(opts)
            return {
                "id": question.id,
                "text": question.text,
                "order": question.order,
                "points": question.points,
                "correct_options_count": sum(1 for o in opts if o.is_correct),
                "selected_option_id": None,
                "options": ExamOptionSerializer(opts, many=True).data,
            }

        seq = obj.question_sequence
        if seq:
            q_by_id = {q.pk: q for q in qs.filter(pk__in=seq)}
            for qid in seq:
                if qid in answered:
                    continue
                q = q_by_id.get(qid)
                if q is not None:
                    return build_payload(q)
            return None

        for q in qs.order_by("order", "id"):
            if q.id not in answered:
                return build_payload(q)
        return None


class AttemptListSerializer(serializers.ModelSerializer):
    test_id = serializers.IntegerField(source="test.id", read_only=True)
    test_title = serializers.CharField(source="test.title", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = TestAttempt
        fields = (
            "id",
            "test_id",
            "test_title",
            "username",
            "full_name",
            "status",
            "started_at",
            "finished_at",
            "score_earned",
            "score_max",
        )

    def get_full_name(self, obj):
        name = obj.user.get_full_name().strip()
        return name if name else obj.user.username


class SubmitAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    option_id = serializers.IntegerField()


class AttemptSessionEventCreateSerializer(serializers.ModelSerializer):
    """POST: логирование hidden/visible/blur/focus во время попытки."""

    class Meta:
        model = AttemptSessionEvent
        fields = (
            "event_type",
            "client_timestamp",
            "duration_away_ms",
            "leave_count",
            "meta",
        )

    def validate_meta(self, value):
        return value if isinstance(value, dict) else {}

    def create(self, validated_data):
        request = self.context["request"]
        attempt = self.context["attempt"]
        from .services import get_request_client_ip

        ip = get_request_client_ip(request)
        return AttemptSessionEvent.objects.create(
            attempt=attempt,
            user_id=attempt.user_id,
            ip_address=ip if ip else None,
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:512],
            **validated_data,
        )


# --- Редактирование тестов (только staff): варианты с is_correct ---


class AnswerOptionStaffReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerOption
        fields = ("id", "text", "is_correct")


class QuestionStaffReadSerializer(serializers.ModelSerializer):
    options = AnswerOptionStaffReadSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ("id", "text", "order", "points", "options")


class TestAuthoringDetailSerializer(serializers.ModelSerializer):
    """Полная карточка теста для администратора (в т.ч. верные ответы)."""

    questions = QuestionStaffReadSerializer(many=True, read_only=True)
    allowed_groups = DepartmentSerializer(many=True, read_only=True)
    question_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Test
        fields = (
            "id",
            "title",
            "description",
            "conduct_starts_at",
            "conduct_ends_at",
            "time_limit_seconds",
            "is_active",
            "allowed_groups",
            "question_count",
            "questions",
            "created_at",
            "updated_at",
        )


class AnswerOptionWriteSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = AnswerOption
        fields = ("id", "text", "is_correct")


class QuestionWriteSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    options = AnswerOptionWriteSerializer(many=True)

    class Meta:
        model = Question
        fields = ("id", "text", "order", "points", "options")

    def validate_options(self, options):
        if len(options) < 2:
            raise serializers.ValidationError(
                "Нужно минимум два варианта ответа на вопрос."
            )
        correct = sum(1 for o in options if o.get("is_correct"))
        if correct != 1:
            raise serializers.ValidationError(
                "Ровно один вариант должен иметь is_correct: true."
            )
        return options


class TestWriteSerializer(serializers.ModelSerializer):
    allowed_group_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
    )
    questions = QuestionWriteSerializer(many=True)

    class Meta:
        model = Test
        fields = (
            "title",
            "description",
            "conduct_starts_at",
            "conduct_ends_at",
            "time_limit_seconds",
            "is_active",
            "allowed_group_ids",
            "questions",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        req = self.context.get("request")
        if req and req.method == "PATCH":
            self.fields["questions"].required = False

    def validate_questions(self, value):
        if not value:
            raise serializers.ValidationError("Нужен хотя бы один вопрос.")
        return value

    def validate(self, attrs):
        req = self.context.get("request")
        qs = attrs.get("questions")
        if (
            req
            and req.method == "PATCH"
            and qs is not None
            and len(qs) == 0
        ):
            raise serializers.ValidationError(
                {"questions": "Передайте хотя бы один вопрос или не передавайте поле."}
            )
        s = attrs.get("conduct_starts_at")
        e = attrs.get("conduct_ends_at")
        if self.instance:
            if "conduct_starts_at" not in attrs:
                s = self.instance.conduct_starts_at
            if "conduct_ends_at" not in attrs:
                e = self.instance.conduct_ends_at
        if s is not None and e is not None and s >= e:
            raise serializers.ValidationError(
                {
                    "conduct_ends_at": "Окончание проведения должно быть позже начала.",
                }
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        questions_data = validated_data.pop("questions")
        group_ids = validated_data.pop("allowed_group_ids", None)
        test = Test.objects.create(**validated_data)
        if group_ids is not None:
            test.allowed_groups.set(group_ids)
        for qd in questions_data:
            options_data = qd.pop("options")
            qd.pop("id", None)
            q = Question.objects.create(test=test, **qd)
            for od in options_data:
                od.pop("id", None)
                AnswerOption.objects.create(question=q, **od)
        return test

    def _sync_options(self, question: Question, options_data):
        kept = set()
        for raw in options_data:
            od = dict(raw)
            oid = od.pop("id", None)
            text = od["text"]
            is_correct = od["is_correct"]
            if oid and AnswerOption.objects.filter(pk=oid, question=question).exists():
                opt = AnswerOption.objects.get(pk=oid)
                opt.text = text
                opt.is_correct = is_correct
                opt.save()
                kept.add(opt.pk)
            else:
                opt = AnswerOption.objects.create(
                    question=question, text=text, is_correct=is_correct
                )
                kept.add(opt.pk)
        AnswerOption.objects.filter(question=question).exclude(pk__in=kept).delete()

    @transaction.atomic
    def update(self, instance, validated_data):
        questions_data = validated_data.pop("questions", None)
        group_ids = validated_data.pop("allowed_group_ids", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if group_ids is not None:
            instance.allowed_groups.set(group_ids)
        if questions_data is not None:
            if not questions_data:
                raise serializers.ValidationError(
                    {"questions": "Нужен хотя бы один вопрос."}
                )
            kept_q = set()
            for q_item in questions_data:
                qid = q_item.get("id")
                options_data = q_item["options"]
                text = q_item["text"]
                order = q_item.get("order", 0)
                points = q_item.get("points", 1)
                if qid and Question.objects.filter(pk=qid, test=instance).exists():
                    q = Question.objects.get(pk=qid)
                    q.text = text
                    q.order = order
                    q.points = points
                    q.save()
                else:
                    q = Question.objects.create(
                        test=instance, text=text, order=order, points=points
                    )
                kept_q.add(q.pk)
                self._sync_options(q, options_data)
            Question.objects.filter(test=instance).exclude(pk__in=kept_q).delete()
        return instance
