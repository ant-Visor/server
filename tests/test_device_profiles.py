import os
import unittest
from unittest.mock import patch

from app.device_profiles import device_client_options
from app.settings import load_settings


class DeviceProfileTests(unittest.TestCase):
  @patch.dict(os.environ, {"TELEGRAM_DEVICE_PROFILE": ""})
  def test_registration_defaults_to_iphone_metadata(self):
    options = device_client_options(load_settings().device_profile)
    self.assertEqual(options, {
      "device_model": "iPhone 14 Pro Max",
      "system_version": "16.6.1",
      "app_version": "9.6.3",
      "lang_code": "en",
      "system_lang_code": "en-US",
    })

  @patch.dict(os.environ, {"TELEGRAM_DEVICE_PROFILE": "telethon_default"})
  def test_can_use_telethon_metadata_defaults(self):
    self.assertEqual(device_client_options(load_settings().device_profile), {})

  def test_unknown_profile_is_rejected(self):
    with self.assertRaisesRegex(ValueError, "Unknown TELEGRAM_DEVICE_PROFILE"):
      device_client_options("unknown")
