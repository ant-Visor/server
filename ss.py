import os
import asyncio

raw_api_id = os.getenv("TELEGRAM_API_ID", "").strip()
api_id=int(raw_api_id) if raw_api_id else None
api_hash=os.getenv("TELEGRAM_API_HASH", "").strip() or None

try:  # Telethon
  from telethon import TelegramClient, events
  def _build_client(proxy=None, session='session_L2'):
    kwargs = dict(
      device_model="iPhone 14 Pro Max",
      system_version="16.6.1",
      app_version="9.6.3",
      lang_code="en",
      system_lang_code="en-US",
      connection_retries=3,
    )
    if proxy: kwargs['proxy'] = proxy
    return TelegramClient(session, api_id, api_hash, **kwargs)
  client = _build_client()
  client.parse_mode = 'html'
  #SOCKS5_HOST = '127.0.0.1'
  #SOCKS5_PORT = 2080
  #_PROXY = ('socks5', SOCKS5_HOST, SOCKS5_PORT)
  #  client = _build_client(_PROXY)
except Exception as e:
  print(f"[Telethon]: {type(e)}\n!-->{e}")
  exit (0)

async def _main():
  try:
    await client.start()
    client_me = await client.get_me()
    if client_me : print(f"\n[connected] {client_me.first_name}")
  except Exception as e:
      print(f"[Telethon]: {type(e)}\n!-->{e}")
  return


if __name__ == '__main__':
  asyncio.run(_main())
  exit(0)