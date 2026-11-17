import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

from app.catalog import list_modules, validate_selection
from app.security import InvalidWebAppData, verify_webapp_init_data


class WebAppDataTests(unittest.TestCase):
  def make_init_data(self, token: str, values: dict) -> str:
    fields = {**values, "auth_date": str(int(time.time()))}
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)

  def test_accepts_valid_signature_and_returns_telegram_user(self):
    token = "test-token"
    data = self.make_init_data(token, {"query_id": "q1", "user": json.dumps({"id": 123})})
    self.assertEqual(verify_webapp_init_data(data, token)["id"], 123)

  def test_rejects_tampered_data(self):
    token = "test-token"
    data = self.make_init_data(token, {"query_id": "q1", "user": json.dumps({"id": 123})})
    with self.assertRaises(InvalidWebAppData):
      verify_webapp_init_data(data + "&query_id=changed", token)


class CatalogTests(unittest.TestCase):
  def test_catalog_discovers_manifest_directories_and_requires_base(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      for name in ("base", "spaceTW"):
        module_dir = root / name / "1.0.0"
        module_dir.mkdir(parents=True)
        (module_dir / "__init__.py").write_text("", encoding="utf-8")
        (module_dir / "module.json").write_text(
          json.dumps({"name": name, "version": "1.0.0", "required": name == "base"}),
          encoding="utf-8",
        )

      newer = root / "spaceTW" / "1.2.0"
      newer.mkdir()
      (newer / "__init__.py").write_text("", encoding="utf-8")
      (newer / "module.json").write_text(
        json.dumps({"name": "SpaceTW", "version": "1.2.0"}),
        encoding="utf-8",
      )

      catalog = list_modules(root)
      self.assertEqual({item["id"] for item in catalog}, {"base", "spaceTW"})
      self.assertEqual(next(item for item in catalog if item["id"] == "spaceTW")["version"], "1.2.0")
      self.assertEqual(validate_selection(root, ["spaceTW"]), ["base", "spaceTW"])
      with self.assertRaises(ValueError):
        validate_selection(root, ["unknown"])


if __name__ == "__main__":
  unittest.main()
