DEFAULT_DEVICE_PROFILE = "iphone_14_pro_max"

DEVICE_PROFILES = {
  "iphone_14_pro_max": {
    "device_model": "iPhone 14 Pro Max",
    "system_version": "16.6.1",
    "app_version": "9.6.3",
    "lang_code": "en",
    "system_lang_code": "en-US",
  },
  "telethon_default": {},
}


def device_client_options(profile_id: str) -> dict[str, str]:
  try:
    return DEVICE_PROFILES[profile_id].copy()
  except KeyError:
    raise ValueError(f"Unknown TELEGRAM_DEVICE_PROFILE: {profile_id!r}") from None
