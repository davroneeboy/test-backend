from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    AnswerOption,
    AttemptSessionEvent,
    AttemptStatus,
    Question,
    Test,
    TestAttempt,
)
from .permissions import (
    IsAttemptOwnerOrStaff,
    IsStaffOrReadAccessibleTest,
    IsStaffUser,
)
from .serializers import (
    AttemptListSerializer,
    AttemptSessionEventCreateSerializer,
    AttemptSerializer,
    PasswordChangeSerializer,
    SubmitAnswerSerializer,
    TestAuthoringDetailSerializer,
    TestDetailSerializer,
    TestListSerializer,
    TestWriteSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
)
from .services import (
    abandon_attempt,
    complete_attempt,
    start_attempt,
    submit_answer,
    sync_expired_attempt,
    user_can_access_test,
)


def _attempt_queryset_for_serializer():
    """Попытка с ответами, тестом и журналом visibility/focus для AttemptSerializer."""
    return TestAttempt.objects.select_related("user", "test").prefetch_related(
        Prefetch(
            "session_events",
            queryset=AttemptSessionEvent.objects.order_by("created_at"),
        ),
        "responses__question",
        "responses__selected_option",
        "test__questions__options",
    )


def _test_queryset_staff_annotated():
    return Test.objects.prefetch_related(
        "questions__options",
        "allowed_groups",
    ).annotate(question_count=Count("questions", distinct=True))


def load_test_staff(pk: int) -> Test:
    return _test_queryset_staff_annotated().get(pk=pk)


def _filter_tests_by_conduct_schedule(qs):
    """Для сдающих: только внутри окна проведения (пустые границы не режут)."""
    now = timezone.now()
    return qs.filter(
        Q(conduct_starts_at__isnull=True) | Q(conduct_starts_at__lte=now),
        Q(conduct_ends_at__isnull=True) | Q(conduct_ends_at__gte=now),
    )


def _accessible_tests_qs(base, user):
    """Queryset тестов, доступных не-staff пользователю по отделу и расписанию."""
    user_groups = user.groups.values_list("pk", flat=True)
    return (
        _filter_tests_by_conduct_schedule(
            base.filter(is_active=True)
            .annotate(_agc=Count("allowed_groups", distinct=True))
            .filter(Q(_agc=0) | Q(allowed_groups__in=user_groups))
            .distinct()
        ).order_by("?")
    )


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserProfileSerializer(self.user).data
        return data


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [LoginRateThrottle]


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return UserProfileUpdateSerializer
        return UserProfileSerializer


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = PasswordChangeSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        request.user.set_password(ser.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class TestListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsStaffUser()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TestWriteSerializer
        return TestListSerializer

    def get_queryset(self):
        base = Test.objects.annotate(
            question_count=Count("questions", distinct=True)
        ).prefetch_related("allowed_groups")
        user = self.request.user
        if user.is_staff:
            return base.order_by("?")
        return _accessible_tests_qs(base, user)

    def create(self, request, *args, **kwargs):
        serializer = TestWriteSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        test = serializer.save()
        test = load_test_staff(test.pk)
        return Response(
            TestAuthoringDetailSerializer(test, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TestDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsStaffOrReadAccessibleTest]

    def get_serializer_class(self):
        # GET всегда без is_correct у вариантов (и для staff) — правки через PUT/PATCH.
        if self.request.method == "GET":
            return TestDetailSerializer
        return TestWriteSerializer

    def get_queryset(self):
        base = _test_queryset_staff_annotated()
        user = self.request.user
        if user.is_staff:
            return base.order_by("?")
        return _accessible_tests_qs(base, user)

    def update(self, request, *args, **kwargs):
        partial = request.method == "PATCH"
        instance = self.get_object()
        serializer = TestWriteSerializer(
            instance,
            data=request.data,
            partial=partial,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        test = load_test_staff(instance.pk)
        return Response(
            TestAuthoringDetailSerializer(test, context={"request": request}).data
        )


class StartAttemptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        test = get_object_or_404(Test.objects.prefetch_related("allowed_groups"), pk=pk)
        if not request.user.is_staff:
            if not user_can_access_test(request.user, test):
                return Response(
                    {
                        "detail": "Тест недоступен: срок проведения, флаг «активен» или доступ по отделу."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        existing_any = (
            TestAttempt.objects.filter(user=request.user, test=test)
            .order_by("-started_at")
            .first()
        )
        if existing_any:
            if existing_any.status == AttemptStatus.IN_PROGRESS:
                sync_expired_attempt(existing_any)
                existing_any.refresh_from_db()
                if existing_any.status == AttemptStatus.IN_PROGRESS:
                    att = _attempt_queryset_for_serializer().get(pk=existing_any.pk)
                    return Response(
                        AttemptSerializer(att, context={"request": request}).data,
                        status=status.HTTP_200_OK,
                    )
            return Response(
                {
                    "detail": "Этот тест можно пройти только один раз. Повторное прохождение недоступно."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        attempt = start_attempt(request.user, test)
        att = _attempt_queryset_for_serializer().get(pk=attempt.pk)
        return Response(
            AttemptSerializer(att, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class AttemptListView(generics.ListAPIView):
    serializer_class = AttemptListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = TestAttempt.objects.select_related("user", "test").order_by("-started_at")
        if not self.request.user.is_staff:
            return qs.filter(user=self.request.user)
        test_id = self.request.query_params.get("test")
        user_id = self.request.query_params.get("user")
        st = self.request.query_params.get("status")
        if test_id:
            qs = qs.filter(test_id=test_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if st:
            qs = qs.filter(status=st)
        return qs


class AttemptDetailView(generics.RetrieveAPIView):
    serializer_class = AttemptSerializer
    permission_classes = [IsAuthenticated, IsAttemptOwnerOrStaff]

    def get_queryset(self):
        return _attempt_queryset_for_serializer()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status == AttemptStatus.IN_PROGRESS:
            sync_expired_attempt(instance)
            instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class SubmitAnswerView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsAttemptOwnerOrStaff]
    queryset = _attempt_queryset_for_serializer()
    lookup_url_kwarg = "pk"

    def post(self, request, *args, **kwargs):
        attempt = self.get_object()
        ser = SubmitAnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        q = get_object_or_404(
            Question,
            pk=ser.validated_data["question_id"],
            test_id=attempt.test_id,
        )
        opt = get_object_or_404(
            AnswerOption,
            pk=ser.validated_data["option_id"],
            question=q,
        )
        submit_answer(attempt, q, opt)
        attempt.refresh_from_db()
        return Response(AttemptSerializer(attempt, context={"request": request}).data)


class CompleteAttemptView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsAttemptOwnerOrStaff]
    queryset = _attempt_queryset_for_serializer()
    lookup_url_kwarg = "pk"

    def post(self, request, *args, **kwargs):
        attempt = self.get_object()
        complete_attempt(attempt)
        attempt.refresh_from_db()
        return Response(AttemptSerializer(attempt, context={"request": request}).data)


class AbandonAttemptView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsAttemptOwnerOrStaff]
    queryset = _attempt_queryset_for_serializer()
    lookup_url_kwarg = "pk"

    def post(self, request, *args, **kwargs):
        attempt = self.get_object()
        abandon_attempt(attempt)
        attempt.refresh_from_db()
        return Response(AttemptSerializer(attempt, context={"request": request}).data)


class AttemptSessionEventCreateView(generics.GenericAPIView):
    """Логирование visibility/blur с клиента во время активной попытки."""

    permission_classes = [IsAuthenticated, IsAttemptOwnerOrStaff]
    queryset = _attempt_queryset_for_serializer()
    lookup_url_kwarg = "pk"

    def post(self, request, *args, **kwargs):
        attempt = self.get_object()
        if attempt.status == AttemptStatus.IN_PROGRESS:
            sync_expired_attempt(attempt)
            attempt.refresh_from_db()
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return Response(
                {
                    "detail": "События принимаются только для попытки в статусе «в процессе»."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = AttemptSessionEventCreateSerializer(
            data=request.data,
            context={"request": request, "attempt": attempt},
        )
        ser.is_valid(raise_exception=True)
        inst = ser.save()
        return Response(
            {
                "id": inst.pk,
                "event_type": inst.event_type,
                "created_at": inst.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})
