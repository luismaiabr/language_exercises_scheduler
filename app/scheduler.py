import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.db import SchedulerDatabase, UserScheduleRow, scheduler_db
from app.email_service import SMTPEmailService, email_service
from app.templates import render_html_email, render_plain_text_email

logger = logging.getLogger(__name__)

class LessonScheduler:
    def __init__(
        self,
        db: Optional[SchedulerDatabase] = None,
        mailer: Optional[SMTPEmailService] = None,
    ):
        self.db = db or scheduler_db
        self.mailer = mailer or email_service
        self._running = False

    def process_due_schedules(self, target_time: Optional[datetime] = None) -> int:
        """
        Scans database for pending user_schedules where when_to_send is today or earlier,
        composes the lesson email with the magic link and exercises, and dispatches via SMTP.
        Returns the number of successfully delivered emails.
        """
        now = target_time or datetime.now(timezone.utc)
        due_schedules = self.db.get_due_schedules(target_time=now)

        if not due_schedules:
            logger.info("No pending schedules due for dispatch.")
            return 0

        logger.info(f"Found {len(due_schedules)} pending lesson schedule(s) due for dispatch.")
        dispatched_count = 0

        for sched in due_schedules:
            try:
                # 1. Fetch user information
                user_info = self.db.get_user_info(sched.user_id)
                user_name = user_info.get("name", "") if user_info else ""
                is_active = user_info.get("is_active", True) if user_info else True

                if not is_active:
                    logger.warning(
                        f"User {sched.email} (ID: {sched.user_id}) is inactive. Cancelling schedule."
                    )
                    self.db.update_schedule_status(sched.id, status="cancelled", error_message="User inactive")
                    continue

                # 2. Fetch exercises and theory summary for this lesson
                exercises = self.db.get_lesson_exercises(sched.user_id, sched.lesson_id)
                theory_summary: Optional[str] = None
                for ex in exercises:
                    if ex.theory_summary:
                        theory_summary = ex.theory_summary
                        break

                # 3. Retrieve or generate the ephemeral capability magic link
                token = self.db.get_or_create_magic_link(
                    user_id=sched.user_id,
                    course_name=sched.course_name,
                    lesson_id=sched.lesson_id,
                )
                if token.startswith("http://") or token.startswith("https://"):
                    magic_link_url = token
                else:
                    magic_link_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/lesson/{token}"

                # 4. Render Email Content
                subject = f"🇩🇪 {sched.course_name} — Lektion #{sched.lesson_id:03d}"
                text_content = render_plain_text_email(
                    student_name=user_name,
                    course_name=sched.course_name,
                    lesson_id=sched.lesson_id,
                    theory_summary=theory_summary,
                    exercises=exercises,
                    magic_link_url=magic_link_url,
                )
                html_content = render_html_email(
                    student_name=user_name,
                    course_name=sched.course_name,
                    lesson_id=sched.lesson_id,
                    theory_summary=theory_summary,
                    exercises=exercises,
                    magic_link_url=magic_link_url,
                )

                # 5. Send via SMTP
                result = self.mailer.send_lesson_email(
                    recipient_email=sched.email,
                    subject=subject,
                    text_content=text_content,
                    html_content=html_content,
                )

                # 6. Update Schedule Status
                if result.success:
                    self.db.update_schedule_status(
                        schedule_id=sched.id,
                        status="sent",
                        sent_at=datetime.now(timezone.utc),
                    )
                    dispatched_count += 1
                    logger.info(
                        f"Successfully dispatched Lesson #{sched.lesson_id} to {sched.email} (Schedule ID: {sched.id})."
                    )
                else:
                    self.db.update_schedule_status(
                        schedule_id=sched.id,
                        status="failed",
                        error_message=result.error or result.message,
                    )
                    logger.error(
                        f"Failed to dispatch Lesson #{sched.lesson_id} to {sched.email}: {result.error}"
                    )

            except Exception as e:
                logger.exception(f"Unexpected error processing schedule {sched.id} for {sched.email}: {e}")
                self.db.update_schedule_status(
                    schedule_id=sched.id,
                    status="failed",
                    error_message=str(e),
                )

        logger.info(f"Dispatch cycle completed: {dispatched_count}/{len(due_schedules)} emails delivered.")
        return dispatched_count

    def run_once(self, target_time: Optional[datetime] = None) -> int:
        """
        Executes a single scheduler cycle for pending lessons due today.
        """
        return self.process_due_schedules(target_time=target_time)

    def start_daemon(self, interval_seconds: Optional[int] = None):
        """
        Runs the scheduler as a continuous background daemon, polling every interval_seconds.
        """
        if settings.INSTANT_DISPATCH:
            logger.info(
                "INSTANT_DISPATCH is enabled. Scheduler daemon polling is disabled (lessons are delivered immediately upon creation)."
            )
            return

        interval = interval_seconds or settings.POLL_INTERVAL_SECONDS
        self._running = True

        def _handle_exit(signum, frame):
            logger.info("Received termination signal. Shutting down scheduler gracefully...")
            self._running = False

        try:
            signal.signal(signal.SIGINT, _handle_exit)
            signal.signal(signal.SIGTERM, _handle_exit)
        except Exception:
            pass

        logger.info(f"Starting language_exercises_scheduler daemon (polling interval: {interval}s)...")

        while self._running:
            try:
                self.process_due_schedules()
            except Exception as e:
                logger.error(f"Error during scheduler cycle: {e}", exc_info=True)

            # Sleep in 1-second chunks to respond quickly to interrupt signals
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("Scheduler daemon stopped.")

scheduler = LessonScheduler()
