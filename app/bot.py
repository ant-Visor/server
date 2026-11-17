import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from .settings import load_settings

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ub.bot")
settings = load_settings()
router = Router(name="control-bot")


@router.message(CommandStart())
async def start(message: Message) -> None:
  if not settings.webapp_url.startswith("https://"):
    await message.answer(
      "Панель регистрации ещё не настроена. Администратору нужно указать публичный HTTPS WEBAPP_URL."
    )
    return

  keyboard = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(
      text="Регистрация / управление",
      web_app=WebAppInfo(url=settings.webapp_url),
    )
  ]])
  await message.answer(
    "Откройте панель, чтобы подключить Telegram-аккаунт и выбрать серверные модули.",
    reply_markup=keyboard,
  )


async def main() -> None:
  if not settings.bot_token:
    raise RuntimeError("BOT_TOKEN is not set")
  bot = Bot(token=settings.bot_token)
  dispatcher = Dispatcher()
  dispatcher.include_router(router)
  try:
    await dispatcher.start_polling(bot)
  finally:
    await bot.session.close()


if __name__ == "__main__":
  asyncio.run(main())
