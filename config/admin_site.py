from django.contrib.admin import AdminSite


class CustomAdminSite(AdminSite):
    def each_context(self, request):
        context = super().each_context(request)
        # Inject proctoring link into "Testing" app in sidebar
        for app in context.get("available_apps", []):
            if app["app_label"] == "testing":
                app["models"].insert(
                    0,
                    {
                        "name": "Прокторинг (live)",
                        "object_name": "Proctoring",
                        "admin_url": "/admin/testing/test/proctoring/",
                        "add_url": None,
                        "view_only": True,
                        "perms": {"view": True},
                    },
                )
                break
        return context
