import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
  bot_token: str
  api_id: int | None
  api_hash: str | None
  webapp_url: str
  users_dir: Path
  catalog_dir: Path
  allowed_modules: frozenset[str]
  control_db: Path
  orchestrator_url: str
  orchestrator_token: str


def load_settings() -> Settings:
  raw_api_id = os.getenv("TELEGRAM_API_ID", "").strip()
  return Settings(
    bot_token=os.getenv("BOT_TOKEN", "").strip(),
    api_id=int(raw_api_id) if raw_api_id else None,
    api_hash=os.getenv("TELEGRAM_API_HASH", "").strip() or None,
    webapp_url=os.getenv("WEBAPP_URL", "").strip().rstrip("/"),
    users_dir=Path(os.getenv("USERS_DIR", "/srv/ub/users")),
    catalog_dir=Path(os.getenv("CATALOG_DIR", "/opt/ub-module-catalog")),
    allowed_modules=frozenset(
      item.strip() for item in os.getenv("SERVER_MODULE_ALLOWLIST", "base,spaceTW").split(",") if item.strip()
    ),
    control_db=Path(os.getenv("CONTROL_DB", "/srv/ub/state/control.sqlite3")),
    orchestrator_url=os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8090").rstrip("/"),
    orchestrator_token=os.getenv("ORCHESTRATOR_TOKEN", ""),
  )
