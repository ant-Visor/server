import hmac
import json
import logging
import os
import re
import shutil
from pathlib import Path

import docker
from docker.errors import NotFound
from docker.types import Mount
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .catalog import list_modules, validate_selection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ub.orchestrator")

app = FastAPI(title="UB worker orchestrator", docs_url=None, redoc_url=None)
users_dir = Path(os.getenv("USERS_DIR", "/srv/ub/users"))
catalog_dir = Path(os.getenv("CATALOG_DIR", "/opt/ub-module-catalog"))
host_users_dir = os.getenv("HOST_USERS_DIR", "").rstrip("/\\")
image_name = os.getenv("WORKER_IMAGE", "ub-worker:local")
api_token = os.getenv("ORCHESTRATOR_TOKEN", "")
allowed_modules = frozenset(
  item.strip() for item in os.getenv("SERVER_MODULE_ALLOWLIST", "base,spaceTW").split(",") if item.strip()
)
docker_client = docker.from_env()


class StartRequest(BaseModel):
  modules: list[str]


def require_token(authorization: str | None) -> None:
  supplied = authorization.removeprefix("Bearer ") if authorization else ""
  if not api_token or not hmac.compare_digest(supplied, api_token):
    raise HTTPException(status_code=401, detail="Unauthorized")


def copy_module_source(module_id: str, version: str, destination: Path) -> None:
  source = catalog_dir / module_id / version
  if not source.is_dir() or not (source / "__init__.py").is_file():
    raise ValueError(f"Module release {module_id}@{version} is not present in the server catalog")

  destination.mkdir(parents=True, exist_ok=True)
  for source_file in source.rglob("*.py"):
    relative = source_file.relative_to(source)
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, target)


def prepare_user(telegram_id: int, selected_modules: list[str]) -> Path:
  user_id = str(telegram_id)
  if not re.fullmatch(r"[1-9][0-9]{0,19}", user_id):
    raise ValueError("Invalid Telegram user ID")
  if not host_users_dir:
    raise ValueError("HOST_USERS_DIR must be an absolute path on the Docker host")
  if not Path(host_users_dir).is_absolute() and not re.match(r"^[A-Za-z]:[/\\]", host_users_dir):
    raise ValueError("HOST_USERS_DIR must be an absolute path on the Docker host")

  validated = validate_selection(catalog_dir, selected_modules, allowed_modules)
  versions = {module["id"]: module["version"] for module in list_modules(catalog_dir, allowed_modules)}
  user_path = users_dir / user_id
  data_dir = user_path / "data"
  modules_dir = user_path / "modules"
  if not all((data_dir / filename).is_file() for filename in ("config.json", "session.session")):
    raise ValueError("Worker data is missing its configuration or Telegram session")
  modules_dir.mkdir(parents=True, exist_ok=True)

  for module_id in validated:
    copy_module_source(module_id, versions[module_id], modules_dir / module_id)

  (data_dir / "enabled-modules.json").write_text(
    json.dumps(validated, indent=2),
    encoding="utf-8",
  )
  (data_dir / "installed-modules.json").write_text(
    json.dumps({module_id: versions[module_id] for module_id in validated}, indent=2),
    encoding="utf-8",
  )

  for path in (user_path, *user_path.rglob("*")):
    try:
      path.chmod(0o700 if path.is_dir() else 0o600)
      os.chown(path, 10001, 10001)
    except (PermissionError, OSError):
      logger.warning("Could not set owner/permissions for %s", path)

  return Path(host_users_dir) / user_id


def find_worker(telegram_id: int):
  name = f"ub-user-{telegram_id}"
  try:
    return docker_client.containers.get(name)
  except NotFound:
    return None


@app.get("/health")
def health() -> dict:
  return {"status": "ok", "worker_image": image_name}


@app.post("/users/{telegram_id}/start")
def start_user(telegram_id: int, request: StartRequest, authorization: str | None = Header(default=None)) -> dict:
  require_token(authorization)
  try:
    validated = validate_selection(catalog_dir, request.modules, allowed_modules)
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc

  worker = find_worker(telegram_id)
  if worker is not None:
    worker.reload()
    if worker.status == "running":
      return {"status": "running", "container": worker.name}
    worker.remove(force=True)

  try:
    host_user_dir = prepare_user(telegram_id, validated)
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc

  worker = docker_client.containers.run(
    image=image_name,
    name=f"ub-user-{telegram_id}",
    command=["python", "-m", "ub"],
    detach=True,
    user="10001:10001",
    environment={
      "PYTHONUNBUFFERED": "1",
      "PYTHONDONTWRITEBYTECODE": "1",
      "UB_NONINTERACTIVE": "1",
      "UB_REQUIRED_MODULES": ",".join(validated),
      "UB_READY_FILE": "/tmp/ub-ready",
    },
    mounts=[
      Mount(target="/app/ub/data", source=str(host_user_dir / "data"), type="bind"),
      Mount(target="/app/ub/modules", source=str(host_user_dir / "modules"), type="bind"),
    ],
    labels={"ub.managed": "true", "ub.telegram_id": str(telegram_id)},
    restart_policy={"Name": "unless-stopped"},
    mem_limit="512m",
    nano_cpus=500_000_000,
    pids_limit=128,
    read_only=True,
    tmpfs={"/tmp": "rw,noexec,nosuid,size=32m"},
    cap_drop=["ALL"],
    security_opt=["no-new-privileges:true"],
  )
  logger.info("Started worker %s for Telegram user %s", worker.name, telegram_id)
  return {"status": "starting", "container": worker.name}


@app.get("/users/{telegram_id}/status")
def user_status(telegram_id: int, authorization: str | None = Header(default=None)) -> dict:
  require_token(authorization)
  worker = find_worker(telegram_id)
  if worker is None:
    return {"status": "not_started"}
  worker.reload()
  health = worker.attrs.get("State", {}).get("Health", {}).get("Status")
  return {"status": worker.status, "health": health, "container": worker.name}
