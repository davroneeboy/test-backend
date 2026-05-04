import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from .models import TestAttempt, AttemptStatus


def _group_name(attempt_id: int) -> str:
    return f"proctoring_{attempt_id}"


class ProctoringConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for live proctoring.

    URL: ws/proctoring/<attempt_id>/
    Query params:
      - role=streamer  (test-taker, sends frames)
      - role=watcher   (curator/staff, receives frames)

    Streamers must own the attempt and it must be IN_PROGRESS.
    Watchers must be staff.
    """

    async def connect(self):
        self.attempt_id = int(self.scope["url_route"]["kwargs"]["attempt_id"])
        self.group = _group_name(self.attempt_id)
        self.role = self._query_param("role")

        if self.role == "streamer":
            if not await self._validate_streamer():
                await self.close(code=4403)
                return
        elif self.role == "watcher":
            if not await self._validate_watcher():
                await self.close(code=4403)
                return
        else:
            await self.close(code=4400)
            return

        if self.role == "watcher":
            await self.channel_layer.group_add(self.group, self.channel_name)

        await self.accept()

    async def disconnect(self, code):
        if self.role == "watcher":
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if self.role != "streamer":
            return

        # Forward raw frame to all watchers in group
        await self.channel_layer.group_send(
            self.group,
            {
                "type": "proctoring.frame",
                "attempt_id": self.attempt_id,
                "frame": text_data,
            },
        )

    async def proctoring_frame(self, event):
        """Called on watcher side when a frame arrives from group_send."""
        await self.send(text_data=event["frame"])

    # ── helpers ──────────────────────────────────────────────────────────────

    def _query_param(self, key: str) -> str:
        query_string = self.scope.get("query_string", b"").decode()
        for part in query_string.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                if k == key:
                    return v
        return ""

    @database_sync_to_async
    def _validate_streamer(self) -> bool:
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            return False
        try:
            attempt = TestAttempt.objects.select_related("user").get(pk=self.attempt_id)
        except TestAttempt.DoesNotExist:
            return False
        return attempt.user_id == user.pk and attempt.status == AttemptStatus.IN_PROGRESS

    @database_sync_to_async
    def _validate_watcher(self) -> bool:
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            return False
        return user.is_staff
