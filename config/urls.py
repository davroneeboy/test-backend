"""
URL configuration for config project.

Админка и nested_admin — под префиксом языка: /admin/ (ru), /uz/admin/ (uz).
API и корень без префикса.
"""
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.utils.translation import gettext_lazy as _

admin.site.site_header = _("Админка тестирования")
admin.site.site_title = _("Тесты")


def root(request):
    return JsonResponse(
        {
            "service": "test-backend",
            "api": "/api/",
            "health": "/api/health/",
            "admin_ru": "/admin/",
            "admin_uz": "/uz/admin/",
            "set_language": "/i18n/setlang/",
        }
    )


urlpatterns = [
    path("", root, name="root"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/", include("testing.urls_api")),
]

urlpatterns += i18n_patterns(
    path("_nested_admin/", include("nested_admin.urls")),
    path("admin/", admin.site.urls),
    prefix_default_language=False,
)
