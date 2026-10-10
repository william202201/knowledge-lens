"""Small Responses API adapter. No credentials are stored or returned to the UI."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    pass


class ResponsesProvider:
    def __init__(self):
        self.key = os.environ.get("OPENAI_API_KEY", "")
        self.model = os.environ.get("OPENAI_MODEL", "")
        if not self.key or not self.model:
            raise ProviderError("Live mode requires OPENAI_API_KEY and OPENAI_MODEL")

    def create(self, **payload) -> dict:
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps({"model": self.model, "store": False, "max_output_tokens": 2000, **payload}).encode(),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                data = json.load(response)
        except HTTPError as error:
            raise ProviderError(f"Model request failed (HTTP {error.code}); check model, access and quota") from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise ProviderError("Model request failed or timed out; no automatic retry was made") from error
        if data.get("status") != "completed":
            raise ProviderError("Model response was incomplete")
        return data


def output_text(response: dict) -> str:
    return "".join(part.get("text", "") for item in response.get("output", [])
                   if item.get("type") == "message" for part in item.get("content", [])
                   if part.get("type") == "output_text")
