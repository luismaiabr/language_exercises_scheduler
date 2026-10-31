# Language Exercises Scheduler (`language_exercises_scheduler`)

An asynchronous automated background scheduler designed to query scheduled German micro-lessons from Supabase PostgreSQL (`user_schedules`), compose structured lesson emails containing daily theory, exercises, and ephemeral zero-auth Magic Links, and dispatch them to enrolled students via SMTP.

---

## 1. System Architecture

```mermaid
flowchart TD
    subgraph Ingestion ["1. Upstream Lesson Generation"]
        Hook[Lesson Ingestion Webhook] --> Core[language_exercises]
        Core -->|New subject detected?| AutoSub[Auto-subscribe ALL users]
        Core -->|1-day interval calculation| SchedTable[(Supabase: user_schedules)]
    end

    subgraph SchedulerService ["2. language_exercises_scheduler"]
        Daemon[Scheduler Engine / Cron] -->|Polls when_to_send <= now()| SchedTable
        Daemon --> FetchContext[Fetch User & Lesson Exercises]
        Daemon --> MagicToken[Get / Issue Ephemeral Magic Link]
        Daemon --> Renderer[Render Dark Monochromatic HTML & Text]
        Daemon --> SMTP[SMTP Server: Hostinger / TLS]
        SMTP --> Student([Student Mailbox])
        Daemon -->|status = 'sent', sent_at = now()| SchedTable
    end
```

---

## 2. Database Schema: `user_schedules`

Created in Supabase PostgreSQL:

```sql
CREATE TABLE IF NOT EXISTS user_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    course_name VARCHAR(100) NOT NULL DEFAULT 'German Theory',
    lesson_id INTEGER NOT NULL CHECK (lesson_id > 0),
    when_to_send TIMESTAMPTZ NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' NOT NULL CHECK (status IN ('pending', 'sent', 'failed', 'cancelled')),
    sent_at TIMESTAMPTZ DEFAULT NULL,
    error_message TEXT DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT uq_user_schedules_user_course_lesson UNIQUE (user_id, course_name, lesson_id)
);

CREATE INDEX IF NOT EXISTS idx_user_schedules_pending ON user_schedules(status, when_to_send);
CREATE INDEX IF NOT EXISTS idx_user_schedules_user_id ON user_schedules(user_id);
CREATE INDEX IF NOT EXISTS idx_user_schedules_email ON user_schedules(email);
```

### Automatic Scheduling & 1-Day Intervals
* **New Subject Creation:** When a new `course_name` is generated, the backend automatically subscribes all existing active users (`is_subscribed = True`) to that subject.
* **1-Day Interval Scheduling:** When a lesson is generated, the system checks each subscribed user's latest scheduled dispatch time for that subject:
  $$\text{when\_to\_send}_{\text{next}} = \text{when\_to\_send}_{\text{latest}} + 1\text{ day}$$
  If no prior schedule exists for that user and subject, `when_to_send` defaults to current timestamp (`now()`).

---

## 3. Configuration (`.env` & `config/scheduler.yaml`)

Configuration is read from environment variables, `.env`, and `config/scheduler.yaml`:

| Key | Description | Default / Example |
| :--- | :--- | :--- |
| `SUPABASE_URL` | Supabase project URL | `https://your-project.supabase.co` |
| `SUPABASE_KEY` | Supabase anon/service role key | `eyJhbG...` |
| `SMTP_HOST` | SMTP server hostname | `smtp.hostinger.com` |
| `SMTP_PORT` | SMTP port (STARTTLS: 587, SSL: 465) | `587` |
| `SMTP_USER` | SMTP username / login email | `education@xseed.space` |
| `SMTP_PASSWORD` | SMTP password / app password | `your-password` |
| `SMTP_FROM_EMAIL` | Outgoing From header address | `education@xseed.space` |
| `SMTP_FROM_NAME` | Display name on outgoing emails | `🇩🇪 Deutsch Daily` |
| `SMTP_USE_TLS` | Upgrade plain connection with STARTTLS | `true` |
| `SMTP_USE_SSL` | Direct SSL/TLS connection | `false` |
| `FRONTEND_BASE_URL` | Base URL for zero-auth Magic Links | `http://localhost:5173` |
| `POLL_INTERVAL_SECONDS` | Daemon poll frequency | `60` |
| `BATCH_SIZE` | Maximum due items processed per cycle | `25` |
| `DRY_RUN` | If true, logs email payload without sending | `false` |

---

## 4. Running the Scheduler

### Option A: One-Shot Execution (Ideal for Linux Cron / Task Scheduler)
Processes all currently due items (`when_to_send <= now()` with `status = 'pending'`), updates their status, and exits:

```bash
python -m app.main --once
```

Example Linux crontab (runs every minute or every hour):
```cron
* * * * * cd /path/to/language_exercises_scheduler && /path/to/venv/bin/python -m app.main --once >> /var/log/scheduler.log 2>&1
```

### Option B: Background Daemon Mode
Runs indefinitely, polling for due schedules every `POLL_INTERVAL_SECONDS`:

```bash
python -m app.main --daemon
```

Override polling interval on the fly (e.g. 30 seconds):
```bash
python -m app.main --daemon --interval 30
```

### Option C: Status Check
Inspects database connectivity, SMTP configuration, and prints all currently due items:

```bash
python -m app.main --status
```

### Option D: Dry-Run Mode
Test the entire workflow without transmitting real emails:

```bash
python -m app.main --once --dry-run -v
```

---

## 5. Testing

A complete test suite is available in `tests/test_scheduler.py`:

```bash
python tests/test_scheduler.py
```

Covered scenarios:
- Configuration and YAML hierarchy loading
- Multi-part plain text and dark-mode HTML email template rendering
- Due schedule dispatch, magic link attachment, and status update to `sent`
- Skipping future scheduled lessons
- Error resilience upon SMTP failure (recording `status = 'failed'` and error trace)
- Cancellation of schedules for inactive students