import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import exchange


class ExchangeCodeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.cwd = Path(self.tempdir.name)
        creds = {
            "installed": {
                "client_id": "cid",
                "client_secret": "secret",
                "token_uri": "https://example.com/token",
            }
        }
        (self.cwd / "credentials.json").write_text(json.dumps(creds), encoding="utf-8")

    @contextmanager
    def _in_temp_cwd(self):
        old_cwd = Path.cwd()
        try:
            os.chdir(self.cwd)
            yield
        finally:
            os.chdir(old_cwd)

    @patch("exchange.requests.post")
    def test_writes_token_json_on_successful_exchange(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "access_token": "access",
            "refresh_token": "refresh",
        }
        mock_post.return_value = response

        with self._in_temp_cwd():
            exchange.exchange_code()

        token_path = self.cwd / "token.json"
        self.assertTrue(token_path.exists())
        token_data = json.loads(token_path.read_text(encoding="utf-8"))
        self.assertEqual(token_data["token"], "access")
        self.assertEqual(token_data["refresh_token"], "refresh")
        self.assertEqual(token_data["client_id"], "cid")
        self.assertEqual(token_data["client_secret"], "secret")
        self.assertEqual(token_data["token_uri"], "https://example.com/token")

    @patch("exchange.requests.post")
    def test_does_not_write_token_json_when_exchange_returns_error(self, mock_post):
        response = Mock()
        response.json.return_value = {"error": "invalid_grant"}
        mock_post.return_value = response

        with self._in_temp_cwd():
            exchange.exchange_code()

        self.assertFalse((self.cwd / "token.json").exists())


if __name__ == "__main__":
    unittest.main()
