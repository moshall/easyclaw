import json
import os
import tempfile
import unittest

import core


class TestProfilesByProvider(unittest.TestCase):
    def setUp(self):
        self._orig_auth_path = core.DEFAULT_AUTH_PROFILES_PATH
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmpdir.name, "openclaw.json")
        self.auth_profiles_path = os.path.join(self.tmpdir.name, "auth-profiles.json")

    def tearDown(self):
        core.DEFAULT_AUTH_PROFILES_PATH = self._orig_auth_path
        self.tmpdir.cleanup()

    def _write_json(self, path, data):
        with open(path, "w") as f:
            json.dump(data, f)

    def test_reads_profiles_from_auth_profiles_store(self):
        self._write_json(self.config_path, {"auth": {"profiles": {}}})
        self._write_json(
            self.auth_profiles_path,
            {
                "version": 1,
                "profiles": {
                    "openrouter:default": {
                        "type": "api_key",
                        "provider": "openrouter",
                        "key": "sk-test",
                    }
                },
            },
        )
        core.DEFAULT_AUTH_PROFILES_PATH = self.auth_profiles_path

        cfg = core.OpenClawConfig(self.config_path)
        pool = cfg.get_profiles_by_provider()

        self.assertIn("openrouter", pool)
        self.assertEqual(len(pool["openrouter"]), 1)
        self.assertEqual(pool["openrouter"][0]["_key"], "openrouter:default")
        self.assertEqual(pool["openrouter"][0]["type"], "api_key")

    def test_merges_same_profile_key_without_double_count(self):
        self._write_json(
            self.config_path,
            {
                "auth": {
                    "profiles": {
                        "openrouter:default": {
                            "provider": "openrouter",
                            "mode": "api_key",
                        }
                    }
                }
            },
        )
        self._write_json(
            self.auth_profiles_path,
            {
                "version": 1,
                "profiles": {
                    "openrouter:default": {
                        "type": "api_key",
                        "provider": "openrouter",
                        "key": "sk-test",
                    }
                },
            },
        )
        core.DEFAULT_AUTH_PROFILES_PATH = self.auth_profiles_path

        cfg = core.OpenClawConfig(self.config_path)
        pool = cfg.get_profiles_by_provider()

        self.assertEqual(len(pool.get("openrouter", [])), 1)
        row = pool["openrouter"][0]
        self.assertEqual(row["mode"], "api_key")
        self.assertEqual(row["type"], "api_key")
        self.assertEqual(row["key"], "sk-test")

    def test_models_by_provider_normalizes_quoted_provider_prefix(self):
        self._write_json(
            self.config_path,
            {
                "agents": {
                    "defaults": {
                        "models": {
                            "'openrouter/test-a'": {},
                            '"openrouter/test-b"': {},
                            "openrouter/test-c": {},
                        }
                    }
                }
            },
        )
        core.DEFAULT_AUTH_PROFILES_PATH = self.auth_profiles_path

        cfg = core.OpenClawConfig(self.config_path)
        pool = cfg.get_models_by_provider()

        self.assertIn("openrouter", pool)
        self.assertNotIn("'openrouter", pool)
        self.assertEqual(len(pool["openrouter"]), 3)


if __name__ == "__main__":
    unittest.main()
