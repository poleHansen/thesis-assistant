from __future__ import annotations

import unittest

from app.model_gateway import ModelGateway


class ModelGatewayTest(unittest.TestCase):
    def test_gateway_falls_back_to_stub_without_keys(self) -> None:
        gateway = ModelGateway()
        result = gateway.complete("writer", "请生成一个摘要。")
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.provider, "stub")
        self.assertIn("离线规则", result.content)


if __name__ == "__main__":
    unittest.main()
