from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import dataclass
from typing import Any
from urllib import error, request


class ProviderError(RuntimeError):
    pass


@dataclass(slots=True)
class ProviderResponse:
    provider: str
    model: str
    content: str
    fallback_used: bool = False


class BaseProvider:
    def __init__(self, provider_name: str, api_base: str, api_key: str | None) -> None:
        self.provider_name = provider_name
        self.api_base = api_base.rstrip("/")
        self._api_key = (api_key or "").strip()

    @property
    def api_key(self) -> str | None:
        return self._api_key or None

    def available(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        raise NotImplementedError

    def embedding(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [round(byte / 255.0, 6) for byte in digest[:16]]


class OpenAICompatibleProvider(BaseProvider):
    def chat(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        if not self.available():
            raise ProviderError(f"{self.provider_name} API key is not configured")

        payload = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")
        req = request.Request(
            f"{self.api_base}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=45) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, socket.timeout) as exc:
            raise ProviderError(f"{self.provider_name} request failed: {exc}") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.provider_name} returned unexpected response") from exc
        return ProviderResponse(provider=self.provider_name, model=model, content=content)


class StubProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__("stub", "stub://local", "")

    def available(self) -> bool:
        return True

    def chat(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        preview = prompt.strip().replace("\n", " ")
        preview = preview[:240]
        content = (
            f"[stub:{model}] {system_prompt[:80]} | "
            f"根据离线规则生成占位内容：{preview}"
        )
        return ProviderResponse(provider=self.provider_name, model=model, content=content)
