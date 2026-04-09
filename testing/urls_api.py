from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from . import api_views

urlpatterns = [
    path("health/", api_views.HealthView.as_view(), name="api-health"),
    path("auth/login/", api_views.LoginView.as_view(), name="api-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="api-token-refresh"),
    path("auth/verify/", TokenVerifyView.as_view(), name="api-token-verify"),
    path("me/", api_views.MeView.as_view(), name="api-me"),
    path("me/password/", api_views.PasswordChangeView.as_view(), name="api-me-password"),
    path("tests/", api_views.TestListView.as_view(), name="api-test-list"),
    path("tests/<int:pk>/", api_views.TestDetailView.as_view(), name="api-test-detail"),
    path(
        "tests/<int:pk>/attempts/",
        api_views.StartAttemptView.as_view(),
        name="api-test-start-attempt",
    ),
    path("attempts/", api_views.AttemptListView.as_view(), name="api-attempt-list"),
    path("attempts/<int:pk>/", api_views.AttemptDetailView.as_view(), name="api-attempt-detail"),
    path(
        "attempts/<int:pk>/answer/",
        api_views.SubmitAnswerView.as_view(),
        name="api-attempt-answer",
    ),
    path(
        "attempts/<int:pk>/complete/",
        api_views.CompleteAttemptView.as_view(),
        name="api-attempt-complete",
    ),
    path(
        "attempts/<int:pk>/abandon/",
        api_views.AbandonAttemptView.as_view(),
        name="api-attempt-abandon",
    ),
    path(
        "attempts/<int:pk>/session-events/",
        api_views.AttemptSessionEventCreateView.as_view(),
        name="api-attempt-session-event",
    ),
]
