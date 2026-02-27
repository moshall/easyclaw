import unittest
from unittest.mock import patch

from core.datasource import _normalize_models, get_official_models


class TestNormalizeModels(unittest.TestCase):
    def test_prefixes_provider_when_model_contains_slash_but_not_provider(self):
        rows = [{"id": "google/gemini-2.5-pro"}]
        got = _normalize_models(rows, "openrouter")
        self.assertEqual(got[0]["key"], "openrouter/google/gemini-2.5-pro")

    def test_keeps_key_when_already_prefixed_with_provider(self):
        rows = [{"key": "openrouter/google/gemini-2.5-pro"}]
        got = _normalize_models(rows, "openrouter")
        self.assertEqual(got[0]["key"], "openrouter/google/gemini-2.5-pro")


class TestGetOfficialModels(unittest.TestCase):
    @patch("core.datasource._load_models_json_provider")
    @patch("core.datasource.run_cli")
    def test_prefers_cli_models_over_models_json_router_placeholder(
        self, mock_run_cli, mock_load_models_json
    ):
        mock_load_models_json.return_value = [{"id": "auto", "name": "OpenRouter Auto"}]
        mock_run_cli.return_value = (
            '{"models":[{"key":"openrouter/a"},{"key":"openrouter/b"}]}',
            "",
            0,
        )

        got = get_official_models("openrouter")
        keys = [m["key"] for m in got]

        self.assertEqual(keys, ["openrouter/a", "openrouter/b"])

    @patch("core.datasource._load_models_json_provider")
    @patch("core.datasource.run_cli")
    def test_falls_back_to_models_json_when_cli_fails(self, mock_run_cli, mock_load_models_json):
        mock_run_cli.return_value = ("", "boom", 1)
        mock_load_models_json.return_value = [{"id": "auto", "name": "OpenRouter Auto"}]

        got = get_official_models("openrouter")
        keys = [m["key"] for m in got]

        self.assertEqual(keys, ["openrouter/auto"])


if __name__ == "__main__":
    unittest.main()
