import json
import os
import tempfile
import unittest
from unittest.mock import patch

import core


class CoreSchemaCompatTest(unittest.TestCase):
    def test_sanitize_payload_removes_security_and_normalizes_models(self):
        raw = {
            "agents": {
                "defaults": {
                    "model": "openrouter/auto",
                    "subagents": {"model": "openrouter/openrouter/free"},
                },
                "list": [
                    {
                        "id": "main",
                        "workspace": "/root/.openclaw/workspace",
                        "security": {"workspaceScope": "workspace-only"},
                        "model": "openrouter/openrouter/free",
                        "subagents": {"model": "openrouter/qwen/qwen3-coder:free"},
                    }
                ],
            }
        }
        fixed, changed = core._sanitize_openclaw_payload(raw)
        self.assertTrue(changed)
        self.assertEqual(fixed["agents"]["defaults"]["model"], {"primary": "openrouter/auto", "fallbacks": []})
        self.assertEqual(
            fixed["agents"]["defaults"]["subagents"]["model"],
            {"primary": "openrouter/openrouter/free", "fallbacks": []},
        )
        row = fixed["agents"]["list"][0]
        self.assertNotIn("security", row)
        self.assertEqual(row["model"], {"primary": "openrouter/openrouter/free", "fallbacks": []})
        self.assertEqual(
            row["subagents"]["model"],
            {"primary": "openrouter/qwen/qwen3-coder:free", "fallbacks": []},
        )

    def test_repair_openclaw_config_if_needed_updates_file(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = os.path.join(td, "openclaw.json")
            bkp = os.path.join(td, "backups")
            os.makedirs(bkp, exist_ok=True)
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "agents": {
                            "defaults": {"model": "openrouter/auto"},
                            "list": [{"id": "main", "security": {"workspaceScope": "workspace-only"}}],
                        }
                    },
                    f,
                )

            with patch.object(core, "DEFAULT_CONFIG_PATH", cfg), patch.object(core, "DEFAULT_BACKUP_DIR", bkp):
                changed = core._repair_openclaw_config_if_needed()

            self.assertTrue(changed)
            with open(cfg, "r", encoding="utf-8") as f:
                fixed = json.load(f)
            self.assertEqual(fixed["agents"]["defaults"]["model"], {"primary": "openrouter/auto", "fallbacks": []})
            self.assertNotIn("security", fixed["agents"]["list"][0])

    def test_security_sidecar_sync_and_inject(self):
        data = {
            "agents": {
                "list": [
                    {
                        "id": "main",
                        "workspace": "/root/.openclaw/workspace",
                        "security": {"workspaceScope": "workspace-only", "controlPlaneCapabilities": ["model.switch"]},
                    }
                ]
            }
        }
        with tempfile.TemporaryDirectory() as td:
            sidecar = os.path.join(td, "agent_security.json")
            with patch.dict(os.environ, {"OPENCLAW_AGENT_SECURITY_PATH": sidecar}, clear=False):
                ok = core._sync_agent_security_store_from_data(data)
                self.assertTrue(ok)

                fixed, _ = core._sanitize_openclaw_payload(data)
                self.assertNotIn("security", fixed["agents"]["list"][0])

                core._inject_agent_security_into_data(fixed)
                restored = fixed["agents"]["list"][0].get("security", {})
                self.assertEqual(restored.get("workspaceScope"), "workspace-only")
                self.assertEqual(restored.get("controlPlaneCapabilities"), ["model.switch"])


if __name__ == "__main__":
    unittest.main()
