import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InvalidWebAppData(ValueError):
  pass


def verify_webapp_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict:
  try:
    values = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    supplied_hash = values.pop("hash")
    auth_date = int(values["auth_date"])
    user = json.loads(values["user"])
  except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
    raise InvalidWebAppData("Malformed Telegram Mini App initData") from exc

  check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
  secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
  expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
  if not hmac.compare_digest(expected_hash, supplied_hash):
    raise InvalidWebAppData("Invalid Telegram Mini App signature")
  if auth_date > time.time() + 60 or time.time() - auth_date > max_age:
    raise InvalidWebAppData("Telegram Mini App authorization expired")
  if not isinstance(user, dict) or not isinstance(user.get("id"), int):
    raise InvalidWebAppData("Telegram user is missing from initData")
  return user
