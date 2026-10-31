import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.db import LessonExerciseRow, SchedulerDatabase, UserScheduleRow
from app.email_service import EmailDispatchResult, SMTPEmailService
from app.scheduler import LessonScheduler
from app.templates import render_html_email, render_plain_text_email

def test_config_loading():
    """Verify scheduler configuration loads defaults and yaml settings."""
    assert settings.SMTP_HOST is not None
    assert settings.SMTP_PORT in (587, 465, 25, 1025)
    assert settings.POLL_INTERVAL_SECONDS > 0
    assert settings.FRONTEND_BASE_URL.startswith("http")

def test_email_templates_render():
    """Verify plain text and HTML email templates render proper contents."""
    uid = uuid4()
    exercises = [
        LessonExerciseRow(
            user_id=uid,
            lesson=1,
            exercise_type="multiple_choice",
            question="Was bedeutet 'Guten Tag'?",
        ),
        LessonExerciseRow(
            user_id=uid,
            lesson=1,
            exercise_type="written",
            question="Schreibe eine kurze Begrüßung.",
        ),
    ]

    magic_url = "http://localhost:5173/lesson/test-token-12345"
    text = render_plain_text_email(
        student_name="Klaus",
        course_name="German Theory",
        lesson_id=1,
        theory_summary="Greetings and basic etiquette.",
        exercises=exercises,
        magic_link_url=magic_url,
    )
    assert "Greetings and basic etiquette." in text
    assert magic_url in text
    assert "Was bedeutet 'Guten Tag'?" not in text

    html = render_html_email(
        student_name="Klaus",
        course_name="German Theory",
        lesson_id=1,
        theory_summary="Greetings and basic etiquette.",
        exercises=exercises,
        magic_link_url=magic_url,
    )
    assert "Lektion #001" in html
    assert "Greetings and basic etiquette." in html
    assert magic_url in html
    assert "#00E5FF" in html
    assert "Was bedeutet 'Guten Tag'?" not in html

def test_process_due_schedules():
    """Verify due schedules are processed and dispatched via SMTP."""
    db = SchedulerDatabase(use_mock=True)
    mailer = SMTPEmailService(is_mock=True)
    sched = LessonScheduler(db=db, mailer=mailer)

    user_id = uuid4()
    db._mock_users[str(user_id)] = {
        "id": str(user_id),
        "name": "Greta Thun",
        "email": "greta@example.com",
        "is_active": True,
    }

    # Add exercise
    db._mock_exercises.append(
        LessonExerciseRow(
            user_id=user_id,
            lesson=5,
            exercise_type="written",
            question="Konjugiere das Verb 'sein'.",
            theory_summary="Verb sein in present tense.",
        )
    )

    # Add schedule due in the past
    now = datetime.now(timezone.utc)
    schedule = UserScheduleRow(
        id=uuid4(),
        user_id=user_id,
        email="greta@example.com",
        course_name="German Theory",
        lesson_id=5,
        when_to_send=now - timedelta(minutes=5),
        status="pending",
    )
    db._mock_schedules.append(schedule)

    count = sched.process_due_schedules(target_time=now)
    assert count == 1
    assert len(mailer.mock_sent_emails) == 1
    assert mailer.mock_sent_emails[0]["to"] == "greta@example.com"
    assert "Lektion #005" in mailer.mock_sent_emails[0]["subject"]

    # Verify schedule updated to sent
    assert schedule.status == "sent"
    assert schedule.sent_at is not None

def test_future_schedules_not_dispatched():
    """Verify schedules with when_to_send in the future are skipped."""
    db = SchedulerDatabase(use_mock=True)
    mailer = SMTPEmailService(is_mock=True)
    sched = LessonScheduler(db=db, mailer=mailer)

    user_id = uuid4()
    db._mock_users[str(user_id)] = {
        "id": str(user_id),
        "name": "Hans",
        "email": "hans@example.com",
        "is_active": True,
    }

    now = datetime.now(timezone.utc)
    future_schedule = UserScheduleRow(
        id=uuid4(),
        user_id=user_id,
        email="hans@example.com",
        course_name="German Theory",
        lesson_id=6,
        when_to_send=now + timedelta(days=1),
        status="pending",
    )
    db._mock_schedules.append(future_schedule)

    count = sched.process_due_schedules(target_time=now)
    assert count == 0
    assert len(mailer.mock_sent_emails) == 0
    assert future_schedule.status == "pending"

def test_smtp_failure_handling():
    """Verify SMTP error updates schedule status to failed."""
    db = SchedulerDatabase(use_mock=True)
    mailer = SMTPEmailService(is_mock=True)
    # Mock send_lesson_email to return failure
    mailer.send_lesson_email = lambda *args, **kwargs: EmailDispatchResult(
        success=False,
        error="Connection refused (mock error)",
    )
    sched = LessonScheduler(db=db, mailer=mailer)

    user_id = uuid4()
    db._mock_users[str(user_id)] = {
        "id": str(user_id),
        "name": "Maria",
        "email": "maria@example.com",
        "is_active": True,
    }

    now = datetime.now(timezone.utc)
    schedule = UserScheduleRow(
        id=uuid4(),
        user_id=user_id,
        email="maria@example.com",
        course_name="German Theory",
        lesson_id=7,
        when_to_send=now - timedelta(minutes=10),
        status="pending",
    )
    db._mock_schedules.append(schedule)

    count = sched.process_due_schedules(target_time=now)
    assert count == 0
    assert schedule.status == "failed"
    assert "Connection refused" in (schedule.error_message or "")

def test_inactive_user_handling():
    """Verify inactive users have their schedule cancelled without sending email."""
    db = SchedulerDatabase(use_mock=True)
    mailer = SMTPEmailService(is_mock=True)
    sched = LessonScheduler(db=db, mailer=mailer)

    user_id = uuid4()
    db._mock_users[str(user_id)] = {
        "id": str(user_id),
        "name": "Inactive User",
        "email": "inactive@example.com",
        "is_active": False,
    }

    now = datetime.now(timezone.utc)
    schedule = UserScheduleRow(
        id=uuid4(),
        user_id=user_id,
        email="inactive@example.com",
        course_name="German Theory",
        lesson_id=8,
        when_to_send=now - timedelta(minutes=1),
        status="pending",
    )
    db._mock_schedules.append(schedule)

    count = sched.process_due_schedules(target_time=now)
    assert count == 0
    assert len(mailer.mock_sent_emails) == 0
    assert schedule.status == "cancelled"

if __name__ == "__main__":
    print("Running language_exercises_scheduler tests...")
    test_config_loading()
    print("[OK] test_config_loading passed.")
    test_email_templates_render()
    print("[OK] test_email_templates_render passed.")
    test_process_due_schedules()
    print("[OK] test_process_due_schedules passed.")
    test_future_schedules_not_dispatched()
    print("[OK] test_future_schedules_not_dispatched passed.")
    test_smtp_failure_handling()
    print("[OK] test_smtp_failure_handling passed.")
    test_inactive_user_handling()
    print("[OK] test_inactive_user_handling passed.")
    print("ALL SCHEDULER TESTS PASSED SUCCESSFULLY!")
