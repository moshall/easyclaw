import unittest
from unittest.mock import patch
from types import SimpleNamespace

from core import write_engine


class TestUpsertProviderApiKey(unittest.TestCase):
    @patch("core.write_engine.set_models_providers")
    @patch("core.write_engine.get_models_providers")
    def test_sets_base_url_only_when_explicit_default_is_provided(self, mock_get, mock_set):
        mock_get.side_effect = [
            {},
            {
                "openrouter": {
                    "apiKey": "sk-test",
                    "baseUrl": "https://openrouter.ai/api/v1",
                    "models": [],
                }
            },
        ]
        mock_set.return_value = True

        ok, err = write_engine.upsert_provider_api_key(
            "openrouter", "sk-test", default_base_url="https://openrouter.ai/api/v1"
        )

        self.assertTrue(ok, err)
        self.assertEqual(err, "")
        mock_set.assert_called_once()
        payload = mock_set.call_args[0][0]
        self.assertIn("openrouter", payload)
        self.assertEqual(payload["openrouter"]["apiKey"], "sk-test")
        self.assertEqual(payload["openrouter"]["baseUrl"], "https://openrouter.ai/api/v1")

    @patch("core.write_engine.set_models_providers")
    @patch("core.write_engine.get_models_providers")
    def test_does_not_inject_base_url_by_default(self, mock_get, mock_set):
        mock_get.side_effect = [
            {},
            {"openrouter": {"apiKey": "__OPENCLAW_REDACTED__", "models": []}},
        ]
        mock_set.return_value = True

        ok, err = write_engine.upsert_provider_api_key("openrouter", "sk-test")

        self.assertTrue(ok, err)
        payload = mock_set.call_args[0][0]
        self.assertNotIn("baseUrl", payload["openrouter"])

    @patch("core.write_engine.set_models_providers")
    @patch("core.write_engine.get_models_providers")
    def test_preserves_existing_base_url(self, mock_get, mock_set):
        mock_get.side_effect = [
            {"openrouter": {"baseUrl": "https://custom.example/v1", "models": []}},
            {
                "openrouter": {
                    "apiKey": "sk-new",
                    "baseUrl": "https://custom.example/v1",
                    "models": [],
                }
            },
        ]
        mock_set.return_value = True

        ok, err = write_engine.upsert_provider_api_key("openrouter", "sk-new")

        self.assertTrue(ok, err)
        self.assertEqual(err, "")
        payload = mock_set.call_args[0][0]
        self.assertEqual(payload["openrouter"]["baseUrl"], "https://custom.example/v1")

    @patch("core.write_engine.set_models_providers")
    @patch("core.write_engine.get_models_providers")
    def test_fails_when_readback_mismatch(self, mock_get, mock_set):
        mock_get.side_effect = [
            {},
            {
                "openrouter": {
                    "apiKey": "different",
                    "baseUrl": "https://openrouter.ai/api/v1",
                    "models": [],
                }
            },
        ]
        mock_set.return_value = True

        ok, err = write_engine.upsert_provider_api_key("openrouter", "sk-test")

        self.assertFalse(ok)
        self.assertIn("read-back failed", err)

    @patch("core.write_engine.set_models_providers")
    @patch("core.write_engine.get_models_providers")
    def test_accepts_redacted_readback(self, mock_get, mock_set):
        mock_get.side_effect = [
            {},
            {
                "openrouter": {
                    "apiKey": "__OPENCLAW_REDACTED__",
                    "baseUrl": "https://openrouter.ai/api/v1",
                    "models": [],
                }
            },
        ]
        mock_set.return_value = True

        ok, err = write_engine.upsert_provider_api_key("openrouter", "sk-real")

        self.assertTrue(ok, err)
        self.assertEqual(err, "")


class TestActivateModelPath(unittest.TestCase):
    @patch("core.write_engine._read_models")
    @patch("core.write_engine.run_cli")
    def test_activate_model_uses_unquoted_bracket_path(self, mock_run_cli, mock_read_models):
        key = "openrouter/ai21/jamba-large-1.7"
        mock_run_cli.return_value = ("ok", "", 0)
        mock_read_models.return_value = {key: {}}

        ok, err = write_engine.activate_model(key)

        self.assertTrue(ok, err)
        called_args = mock_run_cli.call_args[0][0]
        self.assertEqual(called_args[0], "config")
        self.assertEqual(called_args[1], "set")
        self.assertEqual(called_args[2], f"agents.defaults.models[{key}]")

    @patch("core.write_engine.run_cli")
    def test_activate_model_falls_back_to_direct_edit_when_cli_fails(self, mock_run_cli):
        key = "openrouter/fallback-test"
        mock_run_cli.return_value = ("", "boom", 1)
        dummy = SimpleNamespace()
        dummy.data = {"agents": {"defaults": {"models": {}}}}
        dummy.reload = lambda: None
        dummy.save = lambda: True

        with patch("core.write_engine.config", dummy):
            ok, err = write_engine.activate_model(key)

        self.assertTrue(ok, err)
        self.assertIn("direct edit", err)
        models = dummy.data["agents"]["defaults"]["models"]
        self.assertIn(key, models)


class TestCleanupQuotedKeys(unittest.TestCase):
    def test_clean_quoted_model_keys_handles_single_and_double_quotes(self):
        data = {
            "agents": {
                "defaults": {
                    "models": {
                        "'openrouter/test-a'": {"alias": "A"},
                        '"openrouter/test-b"': {"alias": "B"},
                        "openrouter/test-c": {"alias": "C"},
                    }
                }
            }
        }

        dummy = SimpleNamespace()
        dummy.data = data
        dummy.reload = lambda: None
        dummy.save = lambda: True

        with patch("core.write_engine.config", dummy):
            ok, err = write_engine.clean_quoted_model_keys()

        self.assertTrue(ok, err)
        models = data["agents"]["defaults"]["models"]
        self.assertIn("openrouter/test-a", models)
        self.assertIn("openrouter/test-b", models)
        self.assertIn("openrouter/test-c", models)
        self.assertNotIn("'openrouter/test-a'", models)
        self.assertNotIn('"openrouter/test-b"', models)


if __name__ == "__main__":
    unittest.main()
