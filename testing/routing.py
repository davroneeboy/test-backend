from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"^ws/proctoring/(?P<attempt_id>\d+)/$", consumers.ProctoringConsumer.as_asgi()),
]
