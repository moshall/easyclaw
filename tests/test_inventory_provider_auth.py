import unittest
from unittest.mock import patch

try:
    from tui import inventory
except ModuleNotFoundError:
    inventory = None


@unittest.skipIf(inventory is None, "rich/tui dependencies are not installed in this environment")
class TestInventoryProviderAuth(unittest.TestCase):
    def setUp(self):
        inventory.invalidate_plugin_provider_cache()
        inventory.invalidate_models_providers_cache()

    @patch("tui.inventory.provider_auth_plugin_available", return_value=False)
    @patch("tui.inventory.config")
    def test_is_official_provider_false_for_auto_discovered_unknown_provider(
        self, mock_config, _mock_plugin_available
    ):
        mock_config.get_profiles_by_provider.return_value = {}
        self.assertFalse(inventory.is_official_provider("aliyun"))

    @patch("tui.inventory.provider_auth_plugin_available", return_value=False)
    @patch("tui.inventory.config")
    def test_is_official_provider_true_for_builtin_provider(
        self, mock_config, _mock_plugin_available
    ):
        mock_config.get_profiles_by_provider.return_value = {}
        self.assertTrue(inventory.is_official_provider("openrouter"))

    def test_provider_model_count_prefers_configured_models_when_larger(self):
        models_by_provider = {"aliyun": [{"_full_name": "aliyun/a"}]}
        providers_cfg = {"aliyun": {"models": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}}
        self.assertEqual(inventory._provider_model_count("aliyun", models_by_provider, providers_cfg), 3)

    @patch("tui.inventory.run_cli")
    def test_provider_auth_plugin_available_true_when_provider_ids_present(self, mock_run_cli):
        mock_run_cli.return_value = (
            '{"plugins":[{"id":"x","providerIds":["openrouter"]}]}',
            "",
            0,
        )
        self.assertTrue(inventory.provider_auth_plugin_available("openrouter"))

    @patch("tui.inventory.run_cli")
    def test_provider_auth_plugin_available_false_when_missing(self, mock_run_cli):
        mock_run_cli.return_value = ('{"plugins":[{"id":"x","providerIds":[]}]}', "", 0)
        self.assertFalse(inventory.provider_auth_plugin_available("openrouter"))

    @patch("tui.inventory.get_models_providers_cached")
    @patch("tui.inventory.run_cli")
    def test_refresh_official_model_pool_success(self, mock_run_cli, mock_get_cached):
        mock_run_cli.return_value = ('{"models":[{"key":"openrouter/a"},{"key":"openrouter/b"}]}', "", 0)
        mock_get_cached.return_value = {}
        ok, info = inventory.refresh_official_model_pool()
        self.assertTrue(ok)
        self.assertEqual(info, "2")
        mock_get_cached.assert_called_with(force_refresh=True)

    @patch("tui.inventory.get_models_providers_cached")
    @patch("tui.inventory.run_cli")
    def test_refresh_official_model_pool_failure(self, mock_run_cli, mock_get_cached):
        mock_run_cli.return_value = ("", "boom", 1)
        mock_get_cached.return_value = {}
        ok, info = inventory.refresh_official_model_pool()
        self.assertFalse(ok)
        self.assertIn("boom", info)
        mock_get_cached.assert_called_with(force_refresh=True)

    @patch("tui.inventory.run_cli")
    def test_provider_auth_plugin_available_uses_cache(self, mock_run_cli):
        mock_run_cli.return_value = (
            '{"plugins":[{"id":"x","providerIds":["openrouter"]}]}',
            "",
            0,
        )
        self.assertTrue(inventory.provider_auth_plugin_available("openrouter"))
        self.assertTrue(inventory.provider_auth_plugin_available("openrouter"))
        mock_run_cli.assert_called_once()

    @patch("tui.inventory.config")
    @patch("tui.inventory.get_models_providers_cached")
    def test_get_providers_uses_supplied_cfg(self, mock_get_cached, mock_config):
        mock_config.get_profiles_by_provider.return_value = {"openrouter": [{"_key": "x"}]}
        mock_config.get_models_by_provider.return_value = {"openrouter": [{"_full_name": "openrouter/a"}]}
        supplied = {"openrouter": {"apiKey": "x"}, "aliyun": {"apiKey": "y"}}
        providers, profiles, models = inventory.get_providers(supplied)
        self.assertEqual(providers, ["aliyun", "openrouter"])
        self.assertIn("openrouter", profiles)
        self.assertIn("openrouter", models)
        mock_get_cached.assert_not_called()

    def test_is_oauth_provider(self):
        self.assertTrue(inventory.is_oauth_provider("qwen-portal"))
        self.assertFalse(inventory.is_oauth_provider("openrouter"))

    @patch("tui.inventory.pause_enter")
    @patch("tui.inventory.activate_model")
    @patch("tui.inventory.is_official_provider", return_value=True)
    @patch("tui.inventory.safe_input", return_value="openrouter/openrouter/free")
    def test_add_model_manual_wizard_uses_activate_for_official_provider(
        self, _mock_input, _mock_is_official, mock_activate, _mock_pause
    ):
        mock_activate.return_value = (True, "")
        key = inventory.add_model_manual_wizard("openrouter")
        self.assertEqual(key, "openrouter/openrouter/free")
        mock_activate.assert_called_once_with("openrouter/openrouter/free")

    @patch("tui.inventory.pause_enter")
    @patch("tui.inventory._deactivate_model")
    @patch("tui.inventory._activate_model")
    @patch("tui.inventory._read_key")
    def test_activate_models_enter_selects_current_when_empty(
        self, mock_read_key, mock_activate, _mock_deactivate, _mock_pause
    ):
        mock_read_key.side_effect = ["\n"]
        mock_activate.return_value = True
        models = [{"key": "openrouter/a", "name": "A"}]

        inventory.activate_models_with_search("openrouter", models, set())

        mock_activate.assert_called_once_with("openrouter/a")

    @patch("tui.inventory.pause_enter")
    @patch("tui.inventory._deactivate_model")
    @patch("tui.inventory._activate_model")
    @patch("tui.inventory._read_key")
    def test_activate_models_enter_adds_cursor_model_without_explicit_toggle(
        self, mock_read_key, mock_activate, _mock_deactivate, _mock_pause
    ):
        # 模拟：已有激活 a，用户下移到 b 后直接 Enter
        mock_read_key.side_effect = ["j", "\n"]
        mock_activate.return_value = (True, "")
        models = [
            {"key": "openrouter/a", "name": "A"},
            {"key": "openrouter/b", "name": "B"},
        ]

        inventory.activate_models_with_search("openrouter", models, {"openrouter/a"})

        mock_activate.assert_called_once_with("openrouter/b")

    def test_resolve_api_key_auth_choice_for_openrouter(self):
        self.assertEqual(
            inventory.resolve_api_key_auth_choice("openrouter"),
            "openrouter-api-key",
        )

    @patch("tui.inventory.run_cli")
    def test_apply_official_api_key_via_onboard_uses_auth_choice_flag(self, mock_run_cli):
        mock_run_cli.return_value = ('{"ok":true}', "", 0)
        ok, err = inventory.apply_official_api_key_via_onboard(
            provider="openrouter",
            auth_choice="openrouter-api-key",
            api_key="sk-test",
        )
        self.assertTrue(ok, err)
        called_args = mock_run_cli.call_args[0][0]
        self.assertIn("onboard", called_args)
        self.assertIn("--auth-choice", called_args)
        self.assertIn("openrouter-api-key", called_args)
        self.assertIn("--openrouter-api-key", called_args)
        self.assertIn("sk-test", called_args)

    @patch("tui.inventory.pause_enter")
    @patch("tui.inventory.config")
    @patch("tui.inventory.upsert_provider_api_key")
    @patch("tui.inventory.apply_official_api_key_via_onboard")
    @patch("tui.inventory.resolve_api_key_auth_choice")
    @patch("tui.inventory.is_official_provider")
    @patch("tui.inventory.get_models_providers")
    @patch("tui.inventory.Prompt.ask")
    def test_set_provider_apikey_prefers_official_onboard_flow(
        self,
        mock_prompt_ask,
        mock_get_models_providers,
        mock_is_official_provider,
        mock_resolve_auth_choice,
        mock_apply_official,
        mock_upsert,
        mock_config,
        _mock_pause,
    ):
        mock_get_models_providers.return_value = {}
        mock_prompt_ask.return_value = "sk-test"
        mock_is_official_provider.return_value = True
        mock_resolve_auth_choice.return_value = "openrouter-api-key"
        mock_apply_official.return_value = (True, "")
        mock_upsert.return_value = (True, "")
        mock_config.backup.return_value = "/tmp/backup.json"

        inventory.set_provider_apikey("openrouter")

        mock_apply_official.assert_called_once_with("openrouter", "openrouter-api-key", "sk-test")
        mock_upsert.assert_not_called()

    @patch("tui.inventory.set_provider_apikey")
    @patch("tui.inventory.provider_auth_plugin_available", return_value=False)
    @patch("tui.inventory.is_oauth_provider", return_value=False)
    @patch("tui.inventory.is_dry_run", return_value=False)
    @patch("subprocess.run")
    @patch("os.system")
    def test_do_official_auth_falls_back_to_api_key_when_plugin_missing(
        self,
        _mock_os_system,
        mock_subprocess_run,
        _mock_is_dry,
        _mock_is_oauth,
        _mock_plugin_available,
        mock_set_api_key,
    ):
        inventory.do_official_auth("openrouter")
        mock_set_api_key.assert_called_once_with("openrouter")
        mock_subprocess_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
