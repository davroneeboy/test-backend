from datetime import timedelta

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .constants import TEST_CURATOR_GROUP
from .models import AnswerOption, AttemptStatus, Question, Test, TestAttempt
from .services import (
    AttemptError,
    complete_attempt,
    start_attempt,
    submit_answer,
    sync_expired_attempt,
    user_can_access_test,
)


class ConductPeriodTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="stu", password="x")

    def test_full_clean_rejects_inverted_period(self):
        now = timezone.now()
        t = Test(
            title="bad",
            conduct_starts_at=now,
            conduct_ends_at=now - timedelta(hours=1),
        )
        with self.assertRaises(ValidationError):
            t.full_clean()

    def test_save_sets_inactive_when_end_in_past(self):
        past = timezone.now() - timedelta(days=1)
        t = Test(title="expired", is_active=True, conduct_ends_at=past)
        t.save()
        self.assertFalse(t.is_active)

    def test_no_access_before_conduct_starts(self):
        t = Test.objects.create(
            title="soon",
            is_active=True,
            conduct_starts_at=timezone.now() + timedelta(hours=2),
        )
        self.assertFalse(user_can_access_test(self.user, t))

    def test_no_access_after_conduct_ends(self):
        t = Test.objects.create(
            title="late",
            is_active=True,
            conduct_ends_at=timezone.now() - timedelta(minutes=1),
        )
        t.refresh_from_db()
        self.assertFalse(t.is_active)
        self.assertFalse(user_can_access_test(self.user, t))


class AttemptFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="x")
        self.test = Test.objects.create(
            title="T1",
            time_limit_seconds=3600,
            is_active=True,
        )
        self.q1 = Question.objects.create(
            test=self.test, text="Q1", order=1, points=2
        )
        self.q2 = Question.objects.create(
            test=self.test, text="Q2", order=2, points=3
        )
        self.q1_ok = AnswerOption.objects.create(
            question=self.q1, text="Да", is_correct=True
        )
        AnswerOption.objects.create(question=self.q1, text="Нет", is_correct=False)
        self.q2_ok = AnswerOption.objects.create(
            question=self.q2, text="Верно", is_correct=True
        )
        AnswerOption.objects.create(
            question=self.q2, text="Неверно", is_correct=False
        )

    def test_partial_answers_then_timeout_keeps_scores(self):
        attempt = start_attempt(self.user, self.test)
        attempt.deadline_at = timezone.now() + timedelta(seconds=60)
        attempt.save(update_fields=("deadline_at",))

        submit_answer(attempt, self.q1, self.q1_ok)
        attempt.deadline_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=("deadline_at",))

        with self.assertRaises(AttemptError):
            submit_answer(attempt, self.q2, self.q2_ok)

        sync_expired_attempt(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.TIMED_OUT)
        self.assertEqual(attempt.responses.count(), 1)
        self.assertEqual(float(attempt.score_earned), 2.0)
        self.assertEqual(float(attempt.score_max), 5.0)
        self.assertIsNotNone(attempt.finished_at)

    def test_complete_counts_all_answered(self):
        attempt = start_attempt(self.user, self.test)
        submit_answer(attempt, self.q1, self.q1_ok)
        complete_attempt(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.COMPLETED)
        self.assertEqual(float(attempt.score_earned), 2.0)

    def test_second_start_attempt_forbidden_for_user(self):
        attempt = start_attempt(self.user, self.test)
        complete_attempt(attempt)
        with self.assertRaises(AttemptError):
            start_attempt(self.user, self.test)


class TestCuratorGroupTests(TestCase):
    def test_group_and_permissions(self):
        self.assertTrue(
            Permission.objects.filter(codename="change_test").exists(),
            "Права testing должны существовать после миграций",
        )
        g = Group.objects.get(name=TEST_CURATOR_GROUP)
        codes = set(g.permissions.values_list("codename", flat=True))
        self.assertGreater(
            len(codes),
            0,
            f"У группы куратора должны быть права, сейчас: {codes!r}",
        )
        self.assertIn("change_test", codes)
        self.assertIn("view_testattempt", codes)
        self.assertNotIn("change_testattempt", codes)
        self.assertNotIn("view_adminactionlog", codes)
        self.assertNotIn("change_attemptresponse", codes)
        self.assertIn("add_user", codes)
        self.assertNotIn("delete_user", codes)
        self.assertIn("change_group", codes)
