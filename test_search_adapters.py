import json
import tempfile
import unittest
from unittest.mock import patch

from core import search_adapters


class TestSearchAdapters(unittest.TestCase):
    def setUp(self):
        search_adapters.clear_failover_runtime_state()

    def test_load_creates_default(self):
        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/search_adapters.json"
            cfg = search_adapters.load_search_adapters(path=path)
            self.assertIn("providers", cfg)
            self.assertIn("zhipu", cfg["providers"])
            self.assertIn("serper", cfg["providers"])
            self.assertIn("tavily", cfg["providers"])

    def test_update_and_set_active(self):
        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/search_adapters.json"
            ok = search_adapters.update_provider(
                "serper",
                {"apiKey": "sk-1", "enabled": True, "topK": 9},
                path=path,
            )
            self.assertTrue(ok)
            ok = search_adapters.set_active_provider("serper", path=path)
            self.assertTrue(ok)
            cfg = search_adapters.load_search_adapters(path=path)
            self.assertEqual(cfg["active"], "serper")
            self.assertEqual(cfg["providers"]["serper"]["apiKey"], "sk-1")
            self.assertEqual(cfg["providers"]["serper"]["topK"], 9)

    def test_migrate_primary_and_fallbacks_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/search_adapters.json"
            cfg = search_adapters.load_search_adapters(path=path)
            self.assertIn("primary", cfg)
            self.assertIn("fallbacks", cfg)
            self.assertIsInstance(cfg["fallbacks"], list)

    @patch("core.search_adapters.request.urlopen")
    def test_search_with_serper_normalize(self, mock_urlopen):
        payload = {
            "organic": [
                {"title": "A", "link": "https://a.com", "snippet": "sa"},
                {"title": "B", "link": "https://b.com", "snippet": "sb"},
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = body

        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/search_adapters.json"
            search_adapters.update_provider(
                "serper",
                {"apiKey": "k", "enabled": True, "baseUrl": "https://google.serper.dev/search"},
                path=path,
            )
            results = search_adapters.search_with_provider("serper", "openclaw", 2, path=path)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["url"], "https://a.com")

    @patch("core.search_adapters.search_with_provider")
    def test_test_provider_connection(self, mock_search):
        mock_search.return_value = [{"title": "x", "url": "https://x.com", "snippet": "", "source": "t"}]
        ok, msg = search_adapters.test_provider_connection("tavily", path="/tmp/not-used.json")
        self.assertTrue(ok)
        self.assertIn("ok", msg)

    @patch("core.search_adapters.search_with_provider")
    def test_search_with_failover_switch_on_rate_limit(self, mock_search):
        mock_search.side_effect = [
            Exception("429 Too Many Requests"),
            [{"title": "ok", "url": "https://ok.com", "snippet": "s", "source": "tavily"}],
        ]
        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/search_adapters.json"
            search_adapters.update_provider("serper", {"enabled": True, "apiKey": "a"}, path=path)
            search_adapters.update_provider("tavily", {"enabled": True, "apiKey": "b"}, path=path)
            search_adapters.set_primary_provider("serper", path=path)
            search_adapters.set_fallback_providers(["tavily"], path=path)

            res = search_adapters.search_with_failover("OpenClaw", count=3, path=path)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["url"], "https://ok.com")

    @patch("core.search_adapters.search_with_provider")
    def test_search_with_failover_raises_when_all_failed(self, mock_search):
        mock_search.side_effect = Exception("429 rate limit")
        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/search_adapters.json"
            search_adapters.update_provider("serper", {"enabled": True, "apiKey": "a"}, path=path)
            search_adapters.update_provider("tavily", {"enabled": True, "apiKey": "b"}, path=path)
            search_adapters.set_primary_provider("serper", path=path)
            search_adapters.set_fallback_providers(["tavily"], path=path)
            with self.assertRaises(RuntimeError):
                search_adapters.search_with_failover("OpenClaw", count=3, path=path)

    @patch("core.search_adapters.search_with_official_source")
    def test_unified_failover_supports_official_source(self, mock_official):
        mock_official.return_value = [{"title": "x", "url": "https://x.com", "snippet": "", "source": "official:brave"}]
        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/search_adapters.json"
            search_adapters.set_primary_source("official:brave", path=path)
            search_adapters.set_fallback_sources(["adapter:tavily"], path=path)
            res = search_adapters.search_with_unified_failover("OpenClaw", count=3, path=path)
            self.assertEqual(len(res), 1)
            cfg = search_adapters.load_search_adapters(path=path)
            self.assertEqual(cfg.get("activeSource"), "official:brave")

    @patch("core.search_adapters.search_with_provider")
    @patch("core.search_adapters.search_with_official_source")
    def test_unified_failover_switches_from_official_to_adapter(self, mock_official, mock_adapter):
        mock_official.side_effect = Exception("429 rate limit")
        mock_adapter.return_value = [{"title": "ok", "url": "https://ok.com", "snippet": "", "source": "tavily"}]
        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/search_adapters.json"
            search_adapters.update_provider("tavily", {"enabled": True, "apiKey": "k"}, path=path)
            search_adapters.set_primary_source("official:brave", path=path)
            search_adapters.set_fallback_sources(["adapter:tavily"], path=path)
            res = search_adapters.search_with_unified_failover("OpenClaw", count=3, path=path)
            self.assertEqual(res[0]["url"], "https://ok.com")
            cfg = search_adapters.load_search_adapters(path=path)
            self.assertEqual(cfg.get("activeSource"), "adapter:tavily")


if __name__ == "__main__":
    unittest.main()
