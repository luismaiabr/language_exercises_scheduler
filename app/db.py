import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field
from supabase import Client, create_client

from app.config import settings

logger = logging.getLogger(__name__)

class UserScheduleRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    email: str
    course_name: str = "German Theory"
    lesson_id: int
    when_to_send: datetime
    status: str = "pending"
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None

class LessonExerciseRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    lesson: int
    exercise_type: str
    question: str
    options: Optional[Any] = None
    theory_summary: Optional[str] = None

class SchedulerDatabase:
    def __init__(self, use_mock: bool = False):
        self._client: Optional[Client] = None
        # Mock in-memory storage fallback for offline / test runs
        self._mock_schedules: List[UserScheduleRow] = []
        self._mock_exercises: List[LessonExerciseRow] = []
        self._mock_users: Dict[str, Dict[str, Any]] = {}
        self._mock_magic_links: Dict[str, Dict[str, Any]] = {}  # token -> data
        self._mock_subscriptions: List[Dict[str, Any]] = []
        if not use_mock:
            self._init_client()
        else:
            logger.info("SchedulerDatabase initialized in pure mock mode.")

    def _init_client(self):
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_KEY
        is_placeholder = (
            not url
            or "placeholder" in url
            or "your-project" in url
            or not key
            or "placeholder" in key
            or "your-supabase" in key
        )
        if not is_placeholder:
            try:
                self._client = create_client(url, key)
                logger.info("Scheduler Supabase client initialized successfully.")
            except Exception as e:
                logger.warning(f"Could not initialize live Supabase client ({e}). Falling back to memory store.")
                self._client = None
        else:
            logger.info("Using local in-memory store for scheduler (Supabase credentials contain placeholders).")
            self._client = None

    @property
    def client(self) -> Optional[Client]:
        return self._client

    def get_due_schedules(
        self, target_time: Optional[datetime] = None, limit: Optional[int] = None
    ) -> List[UserScheduleRow]:
        """
        Fetch user_schedules rows where status == 'pending' and when_to_send <= end of target day.
        Any pending lessons for today (or overdue from earlier) are dispatched immediately.
        """
        ref_time = target_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        end_of_today = datetime(
            ref_time.year, ref_time.month, ref_time.day, 23, 59, 59, 999999, tzinfo=ref_time.tzinfo
        )
        lim = limit or settings.BATCH_SIZE

        if self.client:
            try:
                res = (
                    self.client.table("user_schedules")
                    .select("*")
                    .eq("status", "pending")
                    .lte("when_to_send", end_of_today.isoformat())
                    .order("when_to_send", desc=False)
                    .limit(lim)
                    .execute()
                )
                return [UserScheduleRow.model_validate(row) for row in res.data]
            except Exception as e:
                logger.warning(f"Live Supabase get_due_schedules failed ({e}). Falling back to memory store.")

        due = []
        for s in self._mock_schedules:
            if s.status == "pending":
                s_time = s.when_to_send if s.when_to_send.tzinfo else s.when_to_send.replace(tzinfo=timezone.utc)
                if s_time <= end_of_today:
                    due.append(s)
        due.sort(key=lambda s: s.when_to_send)
        return due[:lim]

    def get_user_info(self, user_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Fetch user information (name, email, is_active) by user_id.
        """
        uid_str = str(user_id)
        if self.client:
            try:
                res = self.client.table("users").select("id, name, email, is_active").eq("id", uid_str).limit(1).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]
                return None
            except Exception as e:
                logger.warning(f"Live Supabase get_user_info failed ({e}). Falling back to memory store.")

        return self._mock_users.get(uid_str)

    def get_lesson_exercises(self, user_id: UUID, lesson_id: int) -> List[LessonExerciseRow]:
        """
        Fetch exercises for a given user and lesson number.
        """
        uid_str = str(user_id)
        if self.client:
            try:
                res = (
                    self.client.table("exercises")
                    .select("*")
                    .eq("user_id", uid_str)
                    .eq("lesson", lesson_id)
                    .order("created_at", desc=False)
                    .execute()
                )
                return [LessonExerciseRow.model_validate(row) for row in res.data]
            except Exception as e:
                logger.warning(f"Live Supabase get_lesson_exercises failed ({e}). Falling back to memory store.")

        return [
            ex for ex in self._mock_exercises
            if str(ex.user_id) == uid_str and ex.lesson == lesson_id
        ]

    def get_or_create_magic_link(
        self, user_id: UUID, course_name: str, lesson_id: int
    ) -> str:
        """
        Retrieves active magic link token for (user_id, lesson_id), or generates a new one.
        """
        uid_str = str(user_id)
        now = datetime.now(timezone.utc)

        if self.client:
            try:
                res = (
                    self.client.table("magic_links")
                    .select("*")
                    .eq("user_id", uid_str)
                    .eq("lesson", lesson_id)
                    .eq("is_revoked", False)
                    .gte("expires_at", now.isoformat())
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if res.data and len(res.data) > 0:
                    return res.data[0]["token"]

                # If no valid magic link exists, find subscription and create one
                sub_res = (
                    self.client.table("subscriptions")
                    .select("id")
                    .eq("user_id", uid_str)
                    .eq("course_name", course_name)
                    .limit(1)
                    .execute()
                )
                sub_id = sub_res.data[0]["id"] if (sub_res.data and len(sub_res.data) > 0) else None
                if sub_id:
                    token = secrets.token_urlsafe(32)
                    expires_at = now + timedelta(days=7)
                    new_ml = {
                        "id": str(uuid4()),
                        "token": token,
                        "user_id": uid_str,
                        "subscription_id": sub_id,
                        "lesson": lesson_id,
                        "created_at": now.isoformat(),
                        "expires_at": expires_at.isoformat(),
                        "is_revoked": False,
                    }
                    self.client.table("magic_links").insert(new_ml).execute()
                    return token
            except Exception as e:
                logger.warning(f"Live Supabase magic_link lookup failed ({e}). Falling back to memory store.")

        # In-memory fallback
        for token, ml in self._mock_magic_links.items():
            if str(ml.get("user_id")) == uid_str and ml.get("lesson") == lesson_id and not ml.get("is_revoked", False):
                exp = ml.get("expires_at")
                if exp and exp > now:
                    return token

        # Create mock magic link
        new_token = secrets.token_urlsafe(32)
        self._mock_magic_links[new_token] = {
            "token": new_token,
            "user_id": uid_str,
            "course_name": course_name,
            "lesson": lesson_id,
            "created_at": now,
            "expires_at": now + timedelta(days=7),
            "is_revoked": False,
        }
        return new_token

    def update_schedule_status(
        self,
        schedule_id: UUID,
        status: str,
        sent_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ):
        """
        Updates the schedule record to 'sent', 'failed', etc.
        """
        sid_str = str(schedule_id)
        now = sent_at or datetime.now(timezone.utc)

        if self.client:
            try:
                update_data: Dict[str, Any] = {"status": status}
                if status == "sent":
                    update_data["sent_at"] = now.isoformat()
                if error_message:
                    update_data["error_message"] = error_message
                self.client.table("user_schedules").update(update_data).eq("id", sid_str).execute()
                return
            except Exception as e:
                logger.warning(f"Live Supabase update_schedule_status failed ({e}). Falling back to memory store.")

        for s in self._mock_schedules:
            if str(s.id) == sid_str:
                s.status = status
                if status == "sent":
                    s.sent_at = now
                if error_message:
                    s.error_message = error_message
                break

scheduler_db = SchedulerDatabase()
