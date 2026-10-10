import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from knowledge_lens.provider import ProviderError, ResponsesProvider


class Reply:
    def __enter__(self):
        import io
        return io.StringIO(json.dumps({"status": "completed", "output": []}))
    def __exit__(self, *args):
        pass


class ProviderTests(unittest.TestCase):
    def test_missing_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderError):
                ResponsesProvider()

    def test_wire_contract_and_credentials_location(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-key", "OPENAI_MODEL": "test-model"}), patch("knowledge_lens.provider.urlopen", return_value=Reply()) as request:
            ResponsesProvider().create(input="hello")
        req = request.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(body["model"], "test-model")
        self.assertFalse(body["store"])
        self.assertNotIn("test-only-key", req.data.decode())
        self.assertEqual(request.call_args.kwargs["timeout"], 45)

    def test_http_error_is_sanitized_without_retry(self):
        error = HTTPError("https://api.openai.com", 429, "secret upstream body", {}, None)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-key", "OPENAI_MODEL": "test-model"}), patch("knowledge_lens.provider.urlopen", side_effect=error) as request:
            with self.assertRaises(ProviderError) as raised:
                ResponsesProvider().create(input="hello")
        self.assertIn("429", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))
        self.assertEqual(request.call_count, 1)
