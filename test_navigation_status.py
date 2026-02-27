import unittest
from unittest.mock import patch

from tui import navigation


class TestNavigationStatus(unittest.TestCase):
    def test_get_model_provider_status(self):
        with patch.object(navigation, "get_default_model", return_value="openrouter/openrouter/free"), patch.object(
            navigation, "get_fallbacks", return_value=["openrouter/qwen/qwen3-coder:free"]
        ), patch.object(
            navigation, "list_agent_model_override_details", return_value=[{"agent_id": "main", "primary": "openrouter/openrouter/free", "fallbacks": []}]
        ), patch.object(
            navigation, "get_spawn_model_policy", return_value=("", [])
        ):
            status = navigation._get_model_provider_status()
        self.assertEqual(status["default_model"], "openrouter/openrouter/free")
        self.assertEqual(status["fallbacks"], ["openrouter/qwen/qwen3-coder:free"])
        self.assertEqual(status["agent_override_details"][0]["agent_id"], "main")
        self.assertEqual(status["spawn_primary"], "")
        self.assertEqual(status["error"], "")

    def test_get_model_provider_status_on_error(self):
        with patch.object(navigation, "get_default_model", side_effect=RuntimeError("boom")):
            status = navigation._get_model_provider_status()
        self.assertEqual(status["default_model"], "")
        self.assertEqual(status["fallbacks"], [])
        self.assertIn("boom", status["error"])


if __name__ == "__main__":
    unittest.main()
