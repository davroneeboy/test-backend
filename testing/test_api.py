from django.contrib.auth.models import Group, User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import AnswerOption, AttemptSessionEvent, Question, Test


class ApiFlowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="pass12345")
        self.staff = User.objects.create_user(
            username="admin", password="pass12345", is_staff=True
        )
        self.dept = Group.objects.create(name="Отдел А")
        self.user.groups.add(self.dept)

        self.test_obj = Test.objects.create(
            title="API тест",
            time_limit_seconds=600,
            is_active=True,
        )
        self.test_obj.allowed_groups.add(self.dept)

        q = Question.objects.create(
            test=self.test_obj, text="2+2", order=1, points=1
        )
        self.opt_ok = AnswerOption.objects.create(
            question=q, text="4", is_correct=True
        )
        AnswerOption.objects.create(question=q, text="5", is_correct=False)

    def _login(self, username, password):
        url = reverse("api-login")
        r = self.client.post(
            url, {"username": username, "password": password}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("access", r.data)
        self.assertIn("user", r.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

    def test_login_and_me(self):
        self._login("student", "pass12345")
        r = self.client.get(reverse("api-me"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["username"], "student")
        self.assertEqual(r.data["full_name"], "student")
        self.assertEqual(len(r.data["departments"]), 1)
        self.assertEqual(r.data["departments"][0]["name"], "Отдел А")

    def test_patch_me(self):
        self._login("student", "pass12345")
        r = self.client.patch(
            reverse("api-me"),
            {"first_name": "Иван", "email": "ivan@example.com"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Иван")
        me = self.client.get(reverse("api-me"))
        self.assertEqual(me.data["full_name"], "Иван")

    def test_tests_list_and_detail_no_correct_flags(self):
        self._login("student", "pass12345")
        r = self.client.get(reverse("api-test-list"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 1)

        rid = r.data[0]["id"]
        d = self.client.get(reverse("api-test-detail", kwargs={"pk": rid}))
        self.assertEqual(d.status_code, status.HTTP_200_OK)
        opt = d.data["questions"][0]["options"][0]
        self.assertIn("id", opt)
        self.assertIn("text", opt)
        self.assertNotIn("is_correct", opt)

    def test_session_event_logging_during_attempt(self):
        self._login("student", "pass12345")
        r = self.client.post(
            reverse("api-test-start-attempt", kwargs={"pk": self.test_obj.pk})
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        aid = r.data["id"]
        ev = self.client.post(
            reverse("api-attempt-session-event", kwargs={"pk": aid}),
            {
                "event_type": "page_hidden",
                "leave_count": 1,
                "duration_away_ms": None,
                "meta": {"visibilityState": "hidden"},
            },
            format="json",
        )
        self.assertEqual(ev.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ev.data["event_type"], "page_hidden")
        row = AttemptSessionEvent.objects.get(pk=ev.data["id"])
        self.assertEqual(row.attempt_id, aid)
        self.assertEqual(row.user_id, self.user.pk)
        self.assertEqual(row.leave_count, 1)

        vis = self.client.post(
            reverse("api-attempt-session-event", kwargs={"pk": aid}),
            {
                "event_type": "page_visible",
                "leave_count": 1,
                "duration_away_ms": 4200,
            },
            format="json",
        )
        self.assertEqual(vis.status_code, status.HTTP_201_CREATED)

        detail = self.client.get(reverse("api-attempt-detail", kwargs={"pk": aid}))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertIn("session_events", detail.data)
        self.assertEqual(len(detail.data["session_events"]), 2)
        types = {e["event_type"] for e in detail.data["session_events"]}
        self.assertEqual(types, {"page_hidden", "page_visible"})

        self.client.post(reverse("api-attempt-complete", kwargs={"pk": aid}))
        closed = self.client.post(
            reverse("api-attempt-session-event", kwargs={"pk": aid}),
            {"event_type": "page_hidden"},
            format="json",
        )
        self.assertEqual(closed.status_code, status.HTTP_400_BAD_REQUEST)

    def test_start_submit_complete_flow(self):
        self._login("student", "pass12345")
        r = self.client.post(
            reverse("api-test-start-attempt", kwargs={"pk": self.test_obj.pk})
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        aid = r.data["id"]

        r2 = self.client.post(
            reverse("api-attempt-answer", kwargs={"pk": aid}),
            {
                "question_id": self.test_obj.questions.first().pk,
                "option_id": self.opt_ok.pk,
            },
            format="json",
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        r3 = self.client.post(reverse("api-attempt-complete", kwargs={"pk": aid}))
        self.assertEqual(r3.status_code, status.HTTP_200_OK)
        self.assertEqual(r3.data["status"], "completed")

    def test_cannot_start_second_attempt_after_complete(self):
        self._login("student", "pass12345")
        r = self.client.post(
            reverse("api-test-start-attempt", kwargs={"pk": self.test_obj.pk})
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        aid = r.data["id"]
        self.client.post(
            reverse("api-attempt-answer", kwargs={"pk": aid}),
            {
                "question_id": self.test_obj.questions.first().pk,
                "option_id": self.opt_ok.pk,
            },
            format="json",
        )
        detail = self.client.get(reverse("api-attempt-detail", kwargs={"pk": aid}))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["status"], "completed")
        r2 = self.client.post(
            reverse("api-test-start-attempt", kwargs={"pk": self.test_obj.pk})
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("один", r2.data.get("detail", "").lower())

    def test_attempt_list_staff_sees_all(self):
        self._login("student", "pass12345")
        self.client.post(
            reverse("api-test-start-attempt", kwargs={"pk": self.test_obj.pk})
        )
        self.client.credentials()
        self._login("admin", "pass12345")
        r = self.client.get(reverse("api-attempt-list"))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(r.data), 1)

    def test_staff_create_test_includes_correct_flags(self):
        self._login("admin", "pass12345")
        payload = {
            "title": "Из API",
            "description": "",
            "time_limit_seconds": 120,
            "is_active": True,
            "allowed_group_ids": [self.dept.pk],
            "questions": [
                {
                    "text": "2+2=?",
                    "order": 1,
                    "points": 1,
                    "options": [
                        {"text": "4", "is_correct": True},
                        {"text": "5", "is_correct": False},
                        {"text": "3", "is_correct": False},
                        {"text": "22", "is_correct": False},
                    ],
                }
            ],
        }
        r = self.client.post(reverse("api-test-list"), payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        opt = r.data["questions"][0]["options"][0]
        self.assertIn("is_correct", opt)
        self.assertTrue(opt["is_correct"])

        tid = r.data["id"]
        self.client.credentials()
        self._login("student", "pass12345")
        d = self.client.get(reverse("api-test-detail", kwargs={"pk": tid}))
        self.assertEqual(d.status_code, status.HTTP_200_OK)
        opt2 = d.data["questions"][0]["options"][0]
        self.assertNotIn("is_correct", opt2)

    def test_staff_also_cannot_start_second_attempt(self):
        self._login("admin", "pass12345")
        r1 = self.client.post(
            reverse("api-test-start-attempt", kwargs={"pk": self.test_obj.pk})
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        aid = r1.data["id"]
        self.client.post(reverse("api-attempt-complete", kwargs={"pk": aid}))
        r2 = self.client.post(
            reverse("api-test-start-attempt", kwargs={"pk": self.test_obj.pk})
        )
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resume_returns_progress_and_next_question(self):
        q2 = Question.objects.create(
            test=self.test_obj, text="3+3", order=2, points=1
        )
        q2_ok = AnswerOption.objects.create(question=q2, text="6", is_correct=True)
        AnswerOption.objects.create(question=q2, text="7", is_correct=False)

        self._login("student", "pass12345")
        started = self.client.post(
            reverse("api-test-start-attempt", kwargs={"pk": self.test_obj.pk})
        )
        self.assertEqual(started.status_code, status.HTTP_201_CREATED)
        aid = started.data["id"]
        nq = started.data["next_question"]
        self.assertIsNotNone(nq)
        first_qid = nq["id"]
        correct_opt = AnswerOption.objects.get(question_id=first_qid, is_correct=True)

        answer = self.client.post(
            reverse("api-attempt-answer", kwargs={"pk": aid}),
            {
                "question_id": first_qid,
                "option_id": correct_opt.pk,
            },
            format="json",
        )
        self.assertEqual(answer.status_code, status.HTTP_200_OK)

        # Имитируем повторный вход: получаем текущую попытку по тому же старт-эндпоинту.
        self.client.credentials()
        self._login("student", "pass12345")
        resumed = self.client.post(
            reverse("api-test-start-attempt", kwargs={"pk": self.test_obj.pk})
        )
        self.assertEqual(resumed.status_code, status.HTTP_200_OK)
        self.assertEqual(resumed.data["id"], aid)
        self.assertEqual(resumed.data["questions_total"], 2)
        self.assertEqual(resumed.data["questions_answered"], 1)
        self.assertEqual(len(resumed.data["responses"]), 1)
        self.assertEqual(
            resumed.data["responses"][0]["selected_option_id"], correct_opt.pk
        )
        second_id = resumed.data["next_question"]["id"]
        self.assertNotEqual(second_id, first_qid)
        self.assertEqual(
            {first_qid, second_id},
            set(self.test_obj.questions.values_list("pk", flat=True)),
        )
        option_ids = [o["id"] for o in resumed.data["next_question"]["options"]]
        other_correct = AnswerOption.objects.get(question_id=second_id, is_correct=True)
        self.assertIn(other_correct.id, option_ids)
