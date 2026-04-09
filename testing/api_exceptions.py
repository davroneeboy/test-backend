from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .services import AttemptError


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, AttemptError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return None
