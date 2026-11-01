import argparse
import logging
import sys
from datetime import datetime, timezone

from app.config import settings
from app.db import scheduler_db
from app.scheduler import scheduler

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def print_status():
    due = scheduler_db.get_due_schedules()
    print("=" * 60)
    print("LANGUAGE EXERCISES SCHEDULER STATUS")
    print("=" * 60)
    print(f"SMTP Host:         {settings.SMTP_HOST}:{settings.SMTP_PORT}")
    print(f"SMTP User:         {settings.SMTP_USER}")
    print(f"SMTP Configured:   {settings.is_smtp_configured}")
    print(f"Instant Dispatch:  {settings.INSTANT_DISPATCH} ({'Scheduler daemon disabled - delivery occurs immediately on creation' if settings.INSTANT_DISPATCH else 'Scheduler daemon active'})")
    print(f"Dry Run Mode:      {settings.DRY_RUN}")
    print(f"Frontend URL:      {settings.FRONTEND_BASE_URL}")
    print(f"Poll Interval:     {settings.POLL_INTERVAL_SECONDS}s")
    print(f"Current UTC Time:  {datetime.now(timezone.utc).isoformat()}")
    print(f"Pending Due Items: {len(due)}")
    print("=" * 60)
    for s in due:
        print(f"- [Due] User: {s.email} | Course: {s.course_name} | Lesson: #{s.lesson_id} | When: {s.when_to_send}")

def main():
    parser = argparse.ArgumentParser(
        description="Language Exercises SMTP Email Scheduler: Automatically sends daily lessons & magic links"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process currently due schedules once and exit immediately (ideal for cron jobs)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously as a background daemon, polling on configured intervals",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check and display current scheduler configuration and due schedules",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Override polling interval in seconds for daemon mode",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without dispatching real SMTP emails (mock logging only)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug level logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.dry_run:
        settings.DRY_RUN = True

    if args.status:
        print_status()
        sys.exit(0)

    if args.once:
        count = scheduler.process_due_schedules()
        print(f"Dispatched {count} email(s).")
        sys.exit(0)

    # Default mode or explicit --daemon
    interval = args.interval or settings.POLL_INTERVAL_SECONDS
    scheduler.start_daemon(interval_seconds=interval)

if __name__ == "__main__":
    main()
