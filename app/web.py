import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .auth import AuthManager
from .catalog import list_modules, validate_selection
from .orchestrator_client import OrchestratorClient
from .security import InvalidWebAppData, verify_webapp_init_data
from .settings import load_settings
from .storage import UserStore

logger = logging.getLogger(__name__)
settings = load_settings()
store = UserStore(settings.control_db)
orchestrator = OrchestratorClient(settings.orchestrator_url, settings.orchestrator_token)
auth_manager = AuthManager(settings, store, orchestrator)
app = FastAPI(title="UB registration", docs_url=None, redoc_url=None)
web_root = Path(__file__).parent / "webapp"


class AuthStart(BaseModel):
  init_data: str
  phone: str
  modules: list[str] = Field(default_factory=lambda: ["base", "spaceTW"])


class AuthCode(BaseModel):
  init_data: str
  code: str


class AuthPassword(BaseModel):
  init_data: str
  password: str


def _telegram_user(init_data: str) -> int:
  if not settings.bot_token:
    raise HTTPException(status_code=503, detail="Bot is not configured")
  try:
    user = verify_webapp_init_data(init_data, settings.bot_token)
  except InvalidWebAppData as exc:
    raise HTTPException(status_code=401, detail=str(exc)) from exc
  return user["id"]


@app.on_event("startup")
async def startup() -> None:
  await store.initialize()


@app.get("/health")
async def health() -> dict:
  return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
  return FileResponse(web_root / "index.html")


@app.get("/api/modules")
async def modules(init_data: Annotated[str, Header(alias="X-Telegram-Init-Data")]) -> list[dict]:
  _telegram_user(init_data)
  return list_modules(settings.catalog_dir, settings.allowed_modules)


@app.post("/api/auth/start")
async def auth_start(request: AuthStart) -> dict:
  telegram_id = _telegram_user(request.init_data)
  try:
    selected = validate_selection(settings.catalog_dir, request.modules, settings.allowed_modules)
    return await auth_manager.start(telegram_id, request.phone, selected)
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  except RuntimeError as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/auth/code")
async def auth_code(request: AuthCode) -> dict:
  telegram_id = _telegram_user(request.init_data)
  try:
    return await auth_manager.submit_code(telegram_id, request.code)
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  except RuntimeError as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/auth/password")
async def auth_password(request: AuthPassword) -> dict:
  telegram_id = _telegram_user(request.init_data)
  try:
    return await auth_manager.submit_password(telegram_id, request.password)
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  except RuntimeError as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/status")
async def status(init_data: Annotated[str, Header(alias="X-Telegram-Init-Data")]) -> dict:
  telegram_id = _telegram_user(init_data)
  record = await store.get(telegram_id)
  if record is None:
    return {"status": "not_registered", "modules": ["base", "spaceTW"]}
  try:
    worker = await orchestrator.user_status(telegram_id)
  except Exception:
    logger.exception("Could not fetch worker status for %s", telegram_id)
    worker = {"status": record["status"]}
  return {**record, "worker": worker}
