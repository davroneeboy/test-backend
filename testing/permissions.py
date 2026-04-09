from rest_framework import permissions

from .services import user_can_access_test


class IsStaffUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class IsStaffOrReadAccessibleTest(permissions.BasePermission):
    """
    GET: staff — любой тест; иначе только активный и с доступом по отделам.
    POST/PUT/PATCH/DELETE: только staff.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            if request.user.is_staff:
                return True
            return user_can_access_test(request.user, obj)
        return bool(request.user and request.user.is_staff)


class IsTestAccessibleForUser(permissions.BasePermission):
    """Чтение теста: активен и (для не-staff) есть доступ по отделам."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return user_can_access_test(request.user, obj)


class IsAttemptOwnerOrStaff(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return obj.user_id == request.user.id
