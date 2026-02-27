import os
import unittest
from unittest.mock import patch

os.environ.setdefault("WEB_API_TOKEN", "test-token")

try:
    from fastapi.testclient import TestClient
    _HAS_TESTCLIENT = True
except Exception:
    TestClient = None  # type: ignore
    _HAS_TESTCLIENT = False

from web.app import app


@unittest.skipUnless(_HAS_TESTCLIENT, "fastapi.testclient/httpx not installed")
class WebPanelApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_root_page_available(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("EasyClaw Web 面板", resp.text)

    def test_state_requires_token(self):
        resp = self.client.get("/api/state")
        self.assertEqual(resp.status_code, 422)

    def test_state_with_token(self):
        resp = self.client.get("/api/state", headers={"X-Claw-Token": "test-token"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("globalModel", data)
        self.assertIn("agents", data)
        self.assertIn("search", data)

    def test_dispatch_enabled_without_whitelist_defaults_to_allow_all(self):
        with patch("web.app.config.update_subagent_for", return_value=True) as mock_update:
            resp = self.client.post(
                "/api/dispatch",
                headers={"X-Claw-Token": "test-token"},
                json={
                    "agentId": "main",
                    "enabled": True,
                    "allowAgents": [],
                    "maxConcurrent": None,
                    "inheritMaxConcurrent": False,
                },
            )
        self.assertEqual(resp.status_code, 200)
        kwargs = mock_update.call_args.kwargs
        self.assertEqual(kwargs.get("agent_id"), "main")
        self.assertEqual(kwargs.get("allow_agents"), ["*"])


if __name__ == "__main__":
    unittest.main()
