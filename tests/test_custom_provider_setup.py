import unittest
from unittest.mock import patch

from tui import inventory


class TestCustomProviderSetup(unittest.TestCase):
    @patch("tui.inventory.get_custom_models")
    @patch("tui.inventory.set_provider_config")
    @patch("tui.inventory.get_models_providers")
    def test_configure_custom_provider_discovers_and_persists_models(
        self, mock_get_models_providers, mock_set_provider_config, mock_get_custom_models
    ):
        mock_get_models_providers.side_effect = [
            {},
            {"myprov": {"api": "openai-chat", "baseUrl": "https://x/v1", "apiKey": "sk", "models": []}},
        ]
        mock_set_provider_config.return_value = (True, "")
        mock_get_custom_models.return_value = [
            {"key": "myprov/model-a", "name": "Model A"},
            {"key": "model-b", "name": "model-b"},
        ]

        ok, err, discovered_count, discover_err = inventory.configure_custom_provider_config(
            provider="myprov",
            api_proto="openai-chat",
            base_url="https://x/v1",
            api_key="sk",
            discover_models=True,
        )

        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(discovered_count, 2)
        self.assertEqual(discover_err, "")
        self.assertEqual(mock_set_provider_config.call_count, 2)

        second_payload = mock_set_provider_config.call_args_list[1].args[1]
        self.assertEqual(
            second_payload["myprov"]["models"],
            [
                {"id": "model-a", "name": "Model A"},
                {"id": "model-b", "name": "model-b"},
            ],
        )

    @patch("tui.inventory.get_custom_models")
    @patch("tui.inventory.set_provider_config")
    @patch("tui.inventory.get_models_providers")
    def test_configure_custom_provider_skip_discovery(
        self, mock_get_models_providers, mock_set_provider_config, mock_get_custom_models
    ):
        mock_get_models_providers.return_value = {}
        mock_set_provider_config.return_value = (True, "")

        ok, err, discovered_count, discover_err = inventory.configure_custom_provider_config(
            provider="myprov",
            api_proto="openai-chat",
            base_url="https://x/v1",
            api_key="sk",
            discover_models=False,
        )

        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(discovered_count, 0)
        self.assertEqual(discover_err, "")
        mock_get_custom_models.assert_not_called()
        mock_set_provider_config.assert_called_once()

    @patch("tui.inventory.get_custom_models")
    @patch("tui.inventory.set_provider_config")
    @patch("tui.inventory.get_models_providers")
    def test_configure_custom_provider_discovery_failure_does_not_fail_config(
        self, mock_get_models_providers, mock_set_provider_config, mock_get_custom_models
    ):
        mock_get_models_providers.return_value = {}
        mock_set_provider_config.return_value = (True, "")
        mock_get_custom_models.side_effect = RuntimeError("network error")

        ok, err, discovered_count, discover_err = inventory.configure_custom_provider_config(
            provider="myprov",
            api_proto="openai-chat",
            base_url="https://x/v1",
            api_key="sk",
            discover_models=True,
        )

        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(discovered_count, 0)
        self.assertIn("network error", discover_err)

    @patch("tui.inventory.get_custom_models")
    @patch("tui.inventory.set_provider_config")
    @patch("tui.inventory.get_models_providers")
    def test_configure_custom_provider_keeps_api_key_when_second_read_missing_it(
        self, mock_get_models_providers, mock_set_provider_config, mock_get_custom_models
    ):
        mock_get_models_providers.side_effect = [
            {},
            {"myprov": {"models": []}},
        ]
        mock_set_provider_config.return_value = (True, "")
        mock_get_custom_models.return_value = [{"key": "myprov/model-a", "name": "Model A"}]

        ok, err, discovered_count, discover_err = inventory.configure_custom_provider_config(
            provider="myprov",
            api_proto="openai-chat",
            base_url="https://x/v1",
            api_key="sk-real",
            discover_models=True,
        )

        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(discovered_count, 1)
        self.assertEqual(discover_err, "")
        self.assertEqual(mock_set_provider_config.call_count, 2)

        second_payload = mock_set_provider_config.call_args_list[1].args[1]
        self.assertEqual(second_payload["myprov"]["apiKey"], "sk-real")


if __name__ == "__main__":
    unittest.main()
