from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from core.utils.sms import send_sms


class SendSmsTests(SimpleTestCase):
    def test_missing_number_or_body_returns_none(self) -> None:
        self.assertIsNone(send_sms("", "hello"))
        self.assertIsNone(send_sms("+15551234567", ""))

    @override_settings(TWILIO_ACCOUNT_SID=None, TWILIO_AUTH_TOKEN=None, TWILIO_FROM_NUMBER=None)
    def test_missing_credentials_returns_none(self) -> None:
        self.assertIsNone(send_sms("+15551234567", "Hello"))

    @override_settings(
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="token",
        TWILIO_FROM_NUMBER="+15550001111",
    )
    @patch("core.utils.sms.Client")
    def test_successful_send_returns_sid(self, mock_client) -> None:
        stub_message = SimpleNamespace(sid="SM123456789")
        mock_client.return_value.messages.create.return_value = stub_message

        sid = send_sms("+15551234567", "Hello world")

        mock_client.assert_called_once_with("AC123", "token")
        mock_client.return_value.messages.create.assert_called_once_with(
            body="Hello world",
            from_="+15550001111",
            to="+15551234567",
        )
        self.assertEqual(sid, "SM123456789")

    @override_settings(
        TWILIO_ACCOUNT_SID="AC123",
        TWILIO_AUTH_TOKEN="token",
        TWILIO_FROM_NUMBER="+15550001111",
    )
    @patch("core.utils.sms.Client")
    def test_exception_returns_none(self, mock_client) -> None:
        mock_client.return_value.messages.create.side_effect = RuntimeError("Twilio down")

        sid = send_sms("+15551234567", "Hello world")

        self.assertIsNone(sid)
