import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

def load_yaml_config() -> Dict[str, Any]:
    yaml_path = BASE_DIR / "config" / "scheduler.yaml"
    if yaml_path.exists():
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    return {}

_yaml_cfg = load_yaml_config()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase Database
    SUPABASE_URL: str = Field(default="")
    SUPABASE_KEY: str = Field(default="")

    # SMTP Configuration
    SMTP_HOST: str = Field(default_factory=lambda: _yaml_cfg.get("smtp", {}).get("host", "smtp.hostinger.com"))
    SMTP_PORT: int = Field(default_factory=lambda: int(_yaml_cfg.get("smtp", {}).get("port", 587)))
    SMTP_USER: str = Field(default_factory=lambda: _yaml_cfg.get("smtp", {}).get("user", "education@xseed.space"))
    SMTP_PASSWORD: str = Field(default="")
    SMTP_FROM_EMAIL: str = Field(default_factory=lambda: _yaml_cfg.get("smtp", {}).get("from_email", "education@xseed.space"))
    SMTP_FROM_NAME: str = Field(default_factory=lambda: _yaml_cfg.get("smtp", {}).get("from_name", "🇩🇪 Deutsch Daily"))
    SMTP_USE_TLS: bool = Field(default_factory=lambda: bool(_yaml_cfg.get("smtp", {}).get("use_tls", True)))
    SMTP_USE_SSL: bool = Field(default_factory=lambda: bool(_yaml_cfg.get("smtp", {}).get("use_ssl", False)))
    SMTP_TIMEOUT: int = Field(default_factory=lambda: int(_yaml_cfg.get("smtp", {}).get("timeout_seconds", 15)))

    # Scheduler Settings
    FRONTEND_BASE_URL: str = Field(default="http://localhost:5173")
    POLL_INTERVAL_SECONDS: int = Field(default_factory=lambda: int(_yaml_cfg.get("scheduler", {}).get("poll_interval_seconds", 60)))
    MAX_RETRIES: int = Field(default_factory=lambda: int(_yaml_cfg.get("scheduler", {}).get("max_retries", 3)))
    BATCH_SIZE: int = Field(default_factory=lambda: int(_yaml_cfg.get("scheduler", {}).get("batch_size", 25)))
    DRY_RUN: bool = Field(default=False)

    # CORS Allowed Origins
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "https://l.xseed.space",
            "https://l.xeed.space",
            "https://lcore.xseed.space",
            "https://lfront.xseed.space",
            "https://lschedule.xseed.space",
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8000",
            "http://localhost:8001",
        ],
        alias="CORS_ORIGINS",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [item.strip() for item in s.split(",") if item.strip()]
        return []

    @property
    def is_smtp_configured(self) -> bool:
        """Returns True if SMTP has a non-placeholder host, user, and password."""
        return bool(
            self.SMTP_HOST
            and self.SMTP_USER
            and self.SMTP_PASSWORD
            and not self.SMTP_PASSWORD.startswith("your-")
            and not self.SMTP_PASSWORD.startswith("placeholder")
        )

settings = Settings()
