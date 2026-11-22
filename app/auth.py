import asyncio
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
  FloodWaitError,
  PasswordHashInvalidError,
  PhoneCodeExpiredError,
  PhoneCodeInvalidError,
  SessionPasswordNeededError,
)

from .catalog import validate_selection
from .device_profiles import device_client_options
from .orchestrator_client import OrchestratorClient
from .settings import Settings
from .storage import UserStore

logger = logging.getLogger(__name__)


@dataclass
class PendingLogin:
  client: TelegramClient
  phone: str
  phone_code_hash: str
  modules: list[str]
  expires_at: float
  needs_password: bool = False


class AuthManager:
  def __init__(self, settings: Settings, store: UserStore, orchestrator: OrchestratorClient):
    self.settings = settings
    self.store = store
    self.orchestrator = orchestrator
    self.pending: dict[int, PendingLogin] = {}
    self.lock = asyncio.Lock()

  async def start(self, telegram_id: int, phone: str, modules: list[str]) -> dict:
    if not self.settings.api_id or not self.settings.api_hash:
      raise RuntimeError("Server TELEGRAM_API_ID and TELEGRAM_API_HASH are not configured")
    phone = phone.strip()
    if not phone.startswith("+") or not phone[1:].isdigit() or not 8 <= len(phone[1:]) <= 15:
      raise ValueError("Введите номер в международном формате, например +79001234567")
    modules = validate_selection(self.settings.catalog_dir, modules, self.settings.allowed_modules)
    try:
      device_options = device_client_options(self.settings.device_profile)
    except ValueError as exc:
      logger.error("Invalid server Telegram device profile configuration: %s", exc)
      raise RuntimeError("Профиль устройства для авторизации не настроен") from None

    async with self.lock:
      await self._expire_pending()
      if telegram_id in self.pending:
        remaining = int(self.pending[telegram_id].expires_at - time.monotonic()) + 1
        raise ValueError(f"Код уже запрошен. Введите его или повторите запрос через {remaining} сек.")

      user_dir = self.settings.users_dir / str(telegram_id)
      final_session = user_dir / "data" / "session.session"
      if final_session.exists():
        raise ValueError("Для этого Telegram-аккаунта регистрация уже выполнена")

      auth_dir = user_dir / ".auth"
      auth_dir.mkdir(parents=True, exist_ok=True)
      for old_file in auth_dir.glob("login.session*"):
        old_file.unlink(missing_ok=True)
      client = TelegramClient(
        str(auth_dir / "login"), self.settings.api_id, self.settings.api_hash,
        connection_retries=3, **device_options,
      )
      try:
        await client.connect()
        sent_code = await client.send_code_request(phone)
      except FloodWaitError as exc:
        await client.disconnect()
        raise ValueError(f"Telegram просит подождать {exc.seconds} секунд перед повтором") from exc
      except Exception:
        await client.disconnect()
        logger.exception("Failed to request Telegram login code for user %s", telegram_id)
        raise RuntimeError("Не удалось запросить код Telegram. Проверьте номер и попробуйте позже")

      self.pending[telegram_id] = PendingLogin(
        client=client,
        phone=phone,
        phone_code_hash=sent_code.phone_code_hash,
        modules=modules,
        expires_at=time.monotonic() + 600,
      )
    delivery = type(sent_code.type).__name__
    logging.getLogger("uvicorn.error.ub.auth").info(
      "Telegram accepted login code request; profile=%s delivery=%s", self.settings.device_profile, delivery
    )
    hints = {
      "SentCodeTypeApp": "Проверьте служебный чат Telegram в приложении, где этот аккаунт уже открыт.",
      "SentCodeTypeSms": "Проверьте SMS на указанном номере.",
      "SentCodeTypeEmailCode": "Проверьте почту, привязанную к Telegram.",
      "SentCodeTypeCall": "Ожидайте звонок на указанный номер.",
    }
    return {
      "status": "code_sent",
      "message": hints.get(delivery, "Telegram принял запрос. Проверьте подсказки в приложении Telegram."),
    }

  async def submit_code(self, telegram_id: int, code: str) -> dict:
    pending = self.pending.get(telegram_id)
    if pending is None or pending.expires_at <= time.monotonic():
      await self._discard(telegram_id)
      raise ValueError("Срок действия запроса истёк. Начните авторизацию заново")
    try:
      await pending.client.sign_in(
        phone=pending.phone,
        code=code.strip().replace(" ", ""),
        phone_code_hash=pending.phone_code_hash,
      )
    except SessionPasswordNeededError:
      pending.needs_password = True
      return {"status": "password_required", "message": "Введите пароль двухэтапной проверки Telegram"}
    except PhoneCodeInvalidError as exc:
      raise ValueError("Код неверный. Проверьте его и попробуйте ещё раз") from exc
    except PhoneCodeExpiredError as exc:
      await self._discard(telegram_id)
      raise ValueError("Код истёк. Начните авторизацию заново") from exc
    except Exception:
      logger.exception("Telegram code verification failed for user %s", telegram_id)
      raise ValueError("Telegram не принял код. Проверьте код и попробуйте ещё раз")
    return await self._finish(telegram_id, pending)

  async def submit_password(self, telegram_id: int, password: str) -> dict:
    pending = self.pending.get(telegram_id)
    if pending is None or not pending.needs_password or pending.expires_at <= time.monotonic():
      await self._discard(telegram_id)
      raise ValueError("Сессия авторизации истекла. Начните заново")
    try:
      await pending.client.sign_in(password=password)
    except PasswordHashInvalidError as exc:
      raise ValueError("Пароль двухэтапной проверки неверный") from exc
    except Exception:
      logger.exception("Telegram 2FA verification failed for user %s", telegram_id)
      raise ValueError("Telegram не принял пароль двухэтапной проверки")
    return await self._finish(telegram_id, pending)

  async def _finish(self, telegram_id: int, pending: PendingLogin) -> dict:
    user = await pending.client.get_me()
    if user.id != telegram_id:
      await pending.client.disconnect()
      self.pending.pop(telegram_id, None)
      shutil.rmtree(self.settings.users_dir / str(telegram_id) / ".auth", ignore_errors=True)
      raise ValueError("В Mini App и на экране входа должен быть один и тот же Telegram-аккаунт")
    await pending.client.disconnect()

    user_dir = self.settings.users_dir / str(telegram_id)
    data_dir = user_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    auth_session = user_dir / ".auth" / "login.session"
    session_path = data_dir / "session.session"
    if not auth_session.is_file():
      self.pending.pop(telegram_id, None)
      raise RuntimeError("Telegram authorization succeeded but the session file was not created")
    os.replace(auth_session, session_path)
    shutil.rmtree(user_dir / ".auth", ignore_errors=True)
    session_path.chmod(0o600)

    config_path = data_dir / "config.json"
    config_tmp = data_dir / ".config.json.tmp"
    config_tmp.write_text(json.dumps({
      "api_id": self.settings.api_id,
      "api_hash": self.settings.api_hash,
    }, indent=2), encoding="utf-8")
    config_tmp.chmod(0o600)
    os.replace(config_tmp, config_path)
    data_dir.chmod(0o700)

    self.pending.pop(telegram_id, None)
    await self.store.set(telegram_id, "starting", pending.modules)
    try:
      worker = await self.orchestrator.start_user(telegram_id, pending.modules)
    except Exception as exc:
      logger.exception("Could not start user worker %s", telegram_id)
      await self.store.set(telegram_id, "error", pending.modules, str(exc))
      return {
        "status": "error",
        "message": "Авторизация прошла, но worker не запустился. Администратор может повторно запустить его.",
        "telegram_user": user.username or user.first_name,
      }

    await self.store.set(telegram_id, worker["status"], pending.modules)
    return {
      "status": worker["status"],
      "message": "Авторизация успешна, userbot запускается",
      "telegram_user": user.username or user.first_name,
      "modules": pending.modules,
    }

  async def _discard(self, telegram_id: int) -> None:
    pending = self.pending.pop(telegram_id, None)
    if pending:
      try:
        await pending.client.disconnect()
      except Exception:
        logger.exception("Failed to close pending Telegram auth client for %s", telegram_id)
      auth_dir = self.settings.users_dir / str(telegram_id) / ".auth"
      shutil.rmtree(auth_dir, ignore_errors=True)

  async def _expire_pending(self) -> None:
    now = time.monotonic()
    for telegram_id, pending in list(self.pending.items()):
      if pending.expires_at <= now:
        await self._discard(telegram_id)
