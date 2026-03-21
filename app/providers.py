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
    def __init__(
        self,
        provider_name: str,
        api_base: str,
        api_key: str | None,
        api_mode: str = "chat_completions",
    ) -> None:
        super().__init__(provider_name, api_base, api_key)
        mode = (api_mode or "chat_completions").strip().lower()
        if mode in {"chat", "chat_completion", "chat-completions", "chat_completions"}:
            self.api_mode = "chat_completions"
        elif mode in {"responses", "response"}:
            self.api_mode = "responses"
        else:
            # Fallback to chat_completions to avoid breaking at runtime.
            self.api_mode = "chat_completions"

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

        if self.api_mode == "responses":
            # OpenAI "responses" endpoint: map system_prompt -> instructions, prompt -> input.
            payload_obj: dict[str, Any] = {
                "model": model,
                "input": prompt,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            if system_prompt:
                payload_obj["instructions"] = system_prompt
            endpoint = f"{self.api_base}/responses"
        else:
            # Default: OpenAI-compatible chat completions endpoint.
            payload_obj = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            endpoint = f"{self.api_base}/chat/completions"

        payload = json.dumps(payload_obj).encode("utf-8")
        req = request.Request(
            endpoint,
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

        # Extract text depending on API mode.
        try:
            if self.api_mode == "responses":
                # responses API: prefer output/output[0]/content[*]/text
                content_text = ""
                output = body.get("output") or body.get("outputs")
                if isinstance(output, list) and output:
                    first = output[0] or {}
                    content_items = first.get("content") or []
                    if isinstance(content_items, list):
                        fragments: list[str] = []
                        for item in content_items:
                            if not isinstance(item, dict):
                                continue
                            if "text" in item and isinstance(item["text"], str):
                                fragments.append(item["text"])
                            elif "output_text" in item and isinstance(item["output_text"], dict):
                                text_val = item["output_text"].get("text")
                                if isinstance(text_val, str):
                                    fragments.append(text_val)
                        content_text = "".join(fragments).strip()
                # Fallbacks if structure is slightly different.
                if not content_text and isinstance(body.get("content"), str):
                    content_text = str(body["content"])
                if not content_text:
                    raise KeyError("no text content in responses payload")
                content = content_text
            else:
                # chat/completions API.
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
