import asyncio
import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from .models import TestAttempt, AttemptStatus
from .services import sync_expired_attempt

@database_sync_to_async
def sync_expired_attempt_async(attempt_id: int):
    try:
        attempt = TestAttempt.objects.get(pk=attempt_id)
        sync_expired_attempt(attempt)
    except TestAttempt.DoesNotExist:
        pass


def _group_name(attempt_id: int) -> str:
    return f"proctoring_{attempt_id}"


def _parse_jwt_user_id(token: str):
    """Extract user_id from JWT payload without signature verification (trust internal network)."""
    try:
        import base64, json
        payload_b64 = token.split(".")[1]
        # Add padding
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        user_id = payload.get("user_id")
        if user_id is None:
            return None
        return int(user_id)
    except Exception:
        return None


class ProctoringConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for live proctoring.

    URL: ws/proctoring/<attempt_id>/
    Query params:
      - role=streamer  (test-taker) — authenticates via ?token=<JWT>
      - role=watcher   (curator/staff) — authenticates via Django session

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

        self._deadline_task = None
        await self.accept()

        if self.role == "watcher":
            deadline = await self._get_deadline()
            if deadline:
                self._deadline_task = asyncio.ensure_future(self._schedule_expired_notify(deadline))

    async def disconnect(self, code):
        if getattr(self, "_deadline_task", None):
            self._deadline_task.cancel()
        if getattr(self, "role", None) == "watcher":
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if self.role != "streamer":
            return

        if not await self._is_attempt_active():
            await self.channel_layer.group_send(
                self.group,
                {
                    "type": "proctoring.expired",
                    "attempt_id": self.attempt_id,
                },
            )
            await self.close(code=4408)
            return

        frame = text_data if text_data is not None else bytes_data
        if frame is None:
            return

        if isinstance(frame, bytes):
            import base64
            frame = "data:image/png;base64," + base64.b64encode(frame).decode("ascii")

        await self.channel_layer.group_send(
            self.group,
            {
                "type": "proctoring.frame",
                "attempt_id": self.attempt_id,
                "frame": frame,
            },
        )

    async def proctoring_frame(self, event):
        import json
        frame = event["frame"]
        # Если стример шлёт сырой base64 (не JSON), оборачиваем
        try:
            parsed = json.loads(frame)
            if isinstance(parsed, dict) and "type" in parsed:
                await self.send(text_data=frame)
                return
        except (json.JSONDecodeError, TypeError):
            pass
        await self.send(text_data=json.dumps({"type": "frame", "data": frame}))

    async def proctoring_expired(self, event):
        import json
        await self.send(text_data=json.dumps({"type": "expired", "attempt_id": event["attempt_id"]}))

    # ── helpers ──────────────────────────────────────────────────────────────

    def _query_param(self, key: str) -> str:
        from urllib.parse import parse_qs
        query_string = self.scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        values = params.get(key)
        return values[0] if values else ""

    @database_sync_to_async
    def _validate_streamer(self) -> bool:
        # Streamer authenticates via JWT token in query string
        token = self._query_param("token")
        if not token:
            return False
        user_id = _parse_jwt_user_id(token)
        if not user_id:
            return False
        try:
            attempt = TestAttempt.objects.get(pk=self.attempt_id)
        except TestAttempt.DoesNotExist:
            return False
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return False
        if attempt.is_expired():
            sync_expired_attempt(attempt)
            return False
        return attempt.user_id == user_id

    @database_sync_to_async
    def _validate_watcher(self) -> bool:
        # Watcher authenticates via Django session (admin is already logged in)
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            return False
        return user.is_staff

    @database_sync_to_async
    def _get_deadline(self):
        attempt = TestAttempt.objects.filter(pk=self.attempt_id).values("deadline_at").first()
        return attempt["deadline_at"] if attempt else None

    async def _schedule_expired_notify(self, deadline):
        now = timezone.now()
        delay = (deadline - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await sync_expired_attempt_async(self.attempt_id)
        try:
            await self.send(text_data=json.dumps({"type": "expired", "attempt_id": self.attempt_id}))
            await self.close(1000)
        except Exception:
            pass

    @database_sync_to_async
    def _is_attempt_active(self) -> bool:
        attempt = TestAttempt.objects.filter(pk=self.attempt_id).first()
        if not attempt or attempt.status != AttemptStatus.IN_PROGRESS:
            return False
        if attempt.is_expired():
            sync_expired_attempt(attempt)
            return False
        return True
