import asyncio
import os
import sys
from getpass import getpass

from telethon import TelegramClient, __version__


async def main():
  api_id = os.getenv("TELEGRAM_API_ID", "").strip()
  api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
  if not api_id.isascii() or not api_id.isdecimal() or int(api_id) == 0 or not api_hash:
    print("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env before running the test.", file=sys.stderr)
    return 2
  if not sys.stdin.isatty():
    print("Run this test in an interactive terminal with a TTY.", file=sys.stderr)
    return 2

  print(f"Telethon {__version__}; testing login with a fresh session.")
  client = TelegramClient(
    None, int(api_id), api_hash,
    device_model="iPhone 14 Pro Max",
    system_version="16.6.1",
    app_version="9.6.3",
    lang_code="en",
    system_lang_code="en-US",
    connection_retries=3,
  )
  try:
    await client.start(
      code_callback=lambda: getpass("Telegram login code: "),
      password=lambda: getpass("Telegram 2FA password: "),
    )
  finally:
    await client.disconnect()
  print("Telegram login succeeded.")
  return 0


if __name__ == "__main__":
  try:
    sys.exit(asyncio.run(main()))
  except KeyboardInterrupt:
    sys.exit(130)
  except Exception as exc:
    print(f"Telegram login failed: {type(exc).__name__}", file=sys.stderr)
    sys.exit(1)
