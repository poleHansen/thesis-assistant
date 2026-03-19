from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from app.providers import OpenAICompatibleProvider, ProviderError


class ProvidersTest(unittest.TestCase):
    def test_openai_compatible_provider_wraps_timeout_as_provider_error(self) -> None:
        provider = OpenAICompatibleProvider("openai", "https://example.com/v1", "sk-test")

        with patch("app.providers.request.urlopen", side_effect=socket.timeout("timed out")):
            with self.assertRaises(ProviderError) as ctx:
                provider.chat(
                    model="gpt-test",
                    prompt="hello",
                    system_prompt="test",
                    temperature=0.0,
                    max_tokens=16,
                )

        self.assertIn("timed out", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
