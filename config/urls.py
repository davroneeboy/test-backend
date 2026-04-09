"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

admin.site.site_header = "Админка тестирования"
admin.site.site_title = "Тесты"


def root(request):
    return JsonResponse(
        {
            "service": "test-backend",
            "api": "/api/",
            "health": "/api/health/",
            "admin": "/admin/",
        }
    )


urlpatterns = [
    path("", root, name="root"),
    path("_nested_admin/", include("nested_admin.urls")),
    path("admin/", admin.site.urls),
    path("api/", include("testing.urls_api")),
]
