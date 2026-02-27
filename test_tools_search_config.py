import unittest
from unittest.mock import patch

try:
    from tui import tools
except ModuleNotFoundError:
    tools = None


@unittest.skipIf(tools is None, "rich/tui dependencies are not installed in this environment")
class TestToolsSearchConfig(unittest.TestCase):
    def test_parse_supported_search_providers_from_schema(self):
        text = 'Search provider ("brave", "perplexity", "grok", "gemini", or "kimi").'
        got = tools._parse_supported_search_providers_from_schema(text)
        self.assertEqual(got, ["brave", "perplexity", "grok", "gemini", "kimi"])

    def test_parse_supported_search_providers_from_schema_empty(self):
        text = "unrelated text"
        got = tools._parse_supported_search_providers_from_schema(text)
        self.assertEqual(got, [])

    @patch("tui.tools.run_cli")
    @patch("tui.tools.config")
    def test_set_official_search_api_key_brave(self, mock_config, mock_run_cli):
        mock_run_cli.return_value = ("", "", 0)
        mock_config.data = {"tools": {"web": {"search": {}}}}
        mock_config.save.return_value = True
        mock_config.reload.return_value = None
        mock_config.backup.return_value = None

        ok = tools.set_official_search_api_key("brave", "sk-test")
        self.assertTrue(ok)
        called = mock_run_cli.call_args[0][0]
        self.assertEqual(called[:3], ["config", "set", "tools.web.search.apiKey"])

    @patch("tui.tools.config")
    def test_set_search_provider(self, mock_config):
        mock_config.data = {"tools": {"web": {"search": {}}}}
        mock_config.save.return_value = True
        mock_config.reload.return_value = None
        mock_config.backup.return_value = None

        ok = tools.set_search_provider("perplexity")
        self.assertTrue(ok)
        self.assertEqual(mock_config.data["tools"]["web"]["search"]["provider"], "perplexity")

    @patch("tui.tools.run_cli")
    @patch("tui.tools.config")
    def test_set_official_search_api_key_gemini(self, mock_config, mock_run_cli):
        mock_run_cli.return_value = ("", "", 0)
        mock_config.data = {"tools": {"web": {"search": {}}}}
        mock_config.save.return_value = True
        mock_config.reload.return_value = None
        mock_config.backup.return_value = None

        ok = tools.set_official_search_api_key("gemini", "g-test")
        self.assertTrue(ok)
        called = mock_run_cli.call_args[0][0]
        self.assertEqual(called[:3], ["config", "set", "tools.web.search.gemini.apiKey"])

    @patch("tui.tools.run_cli")
    @patch("tui.tools.config")
    def test_set_official_search_api_key_grok(self, mock_config, mock_run_cli):
        mock_run_cli.return_value = ("", "", 0)
        mock_config.data = {"tools": {"web": {"search": {}}}}
        mock_config.save.return_value = True
        mock_config.reload.return_value = None
        mock_config.backup.return_value = None

        ok = tools.set_official_search_api_key("grok", "x-test")
        self.assertTrue(ok)
        called = mock_run_cli.call_args[0][0]
        self.assertEqual(called[:3], ["config", "set", "tools.web.search.grok.apiKey"])

    @patch("tui.tools.run_cli")
    @patch("tui.tools.config")
    def test_set_official_search_api_key_kimi(self, mock_config, mock_run_cli):
        mock_run_cli.return_value = ("", "", 0)
        mock_config.data = {"tools": {"web": {"search": {}}}}
        mock_config.save.return_value = True
        mock_config.reload.return_value = None
        mock_config.backup.return_value = None

        ok = tools.set_official_search_api_key("kimi", "k-test")
        self.assertTrue(ok)
        called = mock_run_cli.call_args[0][0]
        self.assertEqual(called[:3], ["config", "set", "tools.web.search.kimi.apiKey"])

    @patch("tui.tools.read_env_keys")
    @patch("tui.tools.config")
    def test_list_configured_official_search_providers(self, mock_config, mock_read_env):
        mock_config.data = {
            "tools": {
                "web": {
                    "search": {
                        "provider": "brave",
                        "apiKey": "brave_key",
                        "perplexity": {"apiKey": ""},
                        "grok": {"apiKey": "xai_key"},
                    }
                }
            }
        }
        mock_config.reload.return_value = None
        mock_read_env.return_value = {"GEMINI_API_KEY": "gem_env"}

        got = tools.list_configured_official_search_providers(["brave", "perplexity", "grok", "gemini", "kimi"])
        self.assertEqual(got, ["brave", "grok", "gemini"])


if __name__ == "__main__":
    unittest.main()
