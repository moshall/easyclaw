import os
import tempfile
import unittest
from unittest.mock import patch

from tui import routing


class _DummyConfig:
    def __init__(self, workspace_path: str):
        self.data = {
            "agents": {
                "defaults": {"workspace": workspace_path},
                "list": [],
            }
        }

    def save(self):
        return True

    def reload(self):
        return None


class TestRoutingMainAgent(unittest.TestCase):
    def test_dispatch_manageable_agents_prioritizes_main(self):
        cfg = _DummyConfig("/root/.openclaw/workspace")
        cfg.data["agents"]["list"] = [{"id": "worker1"}, {"id": "main"}, {"id": "worker2"}]
        with patch.object(routing, "config", cfg):
            ids = [a.get("id") for a in routing._dispatch_manageable_agents()]
        self.assertEqual(ids, ["main", "worker1", "worker2"])

    def test_agent_id_validation(self):
        self.assertTrue(routing._is_valid_agent_id("main1"))
        self.assertTrue(routing._is_valid_agent_id("agent_alpha-01"))
        self.assertFalse(routing._is_valid_agent_id("1agent"))
        self.assertFalse(routing._is_valid_agent_id("agent name"))

    def test_resolve_agent_id_input(self):
        ids = ["main", "worker_1"]
        self.assertEqual(routing._resolve_agent_id_input(ids, "main"), "main")
        self.assertEqual(routing._resolve_agent_id_input(ids, "MAIN"), "main")
        self.assertEqual(routing._resolve_agent_id_input(ids, "mian"), "")

    def test_next_main_agent_id(self):
        cfg = _DummyConfig("/root/.openclaw/workspace")
        cfg.data["agents"]["list"] = [{"id": "main"}, {"id": "main1"}]
        with patch.object(routing, "config", cfg):
            self.assertEqual(routing._next_main_agent_id(), "main2")

    def test_default_agent_id_for_form_prefers_existing(self):
        agents = [{"id": "main"}, {"id": "main1"}]
        self.assertEqual(routing._default_agent_id_for_form(agents), "main")

    def test_recommended_main_agent_id_prefers_unbound(self):
        cfg = _DummyConfig("/root/.openclaw/workspace")
        cfg.data["agents"]["list"] = [{"id": "main", "workspace": ""}, {"id": "main1", "workspace": "/root/.openclaw/workspace_01"}]
        with patch.object(routing, "config", cfg):
            self.assertEqual(routing._recommended_main_agent_id(), "main")

    def test_next_workspace_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _DummyConfig(os.path.join(tmp, "workspace"))
            cfg.data["agents"]["list"] = [{"id": "main", "workspace": os.path.join(tmp, "workspace")}]
            os.makedirs(os.path.join(tmp, "workspace"), exist_ok=True)
            with patch.object(routing, "config", cfg):
                got = routing._next_workspace_path(cfg.data["agents"]["list"])
            self.assertEqual(got, os.path.join(tmp, "workspace_01"))

    def test_upsert_main_agent_config_creates_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _DummyConfig(os.path.join(tmp, "workspace"))
            ws = os.path.join(tmp, "workspace")
            with patch.object(routing, "config", cfg):
                ok = routing.upsert_main_agent_config(
                    agent_id="main",
                    workspace_path=ws,
                    model_primary="openrouter/openrouter/free",
                    model_fallbacks_csv="openrouter/qwen/qwen3-coder:free",
                    allow_agents=["*"],
                    sub_model_primary="openrouter/stepfun/step-3.5-flash:free",
                    sub_model_fallbacks_csv="",
                    workspace_restricted=True,
                )
            self.assertTrue(ok)
            agents = cfg.data.get("agents", {}).get("list", [])
            self.assertEqual(len(agents), 1)
            self.assertEqual(agents[0]["id"], "main")
            self.assertTrue(os.path.exists(os.path.join(ws, "AGENTS.md")))
            self.assertTrue(os.path.exists(os.path.join(ws, "SOUL.md")))
            self.assertTrue(os.path.exists(os.path.join(ws, "TOOLS.md")))
            self.assertTrue(os.path.exists(os.path.join(ws, "software")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "agents", "main", "agent")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "agents", "main", "sessions")))
            sec = agents[0].get("security", {})
            self.assertEqual(sec.get("workspaceScope"), "workspace-only")
            self.assertEqual(sec.get("controlPlaneCapabilities", []), [])

    def test_upsert_main_agent_config_preserves_unknown_fields_on_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "workspace")
            cfg = _DummyConfig(ws)
            cfg.data["agents"]["list"] = [
                {
                    "id": "main",
                    "workspace": ws,
                    "customMeta": {"x": 1},
                    "notes": "keep-me",
                    "security": {"workspaceScope": "workspace-only", "controlPlaneCapabilities": ["model.switch"]},
                }
            ]
            os.makedirs(ws, exist_ok=True)
            with patch.object(routing, "config", cfg):
                ok = routing.upsert_main_agent_config(
                    agent_id="main",
                    workspace_path=ws,
                    model_primary="openrouter/openrouter/free",
                    workspace_restricted=False,
                )
            self.assertTrue(ok)
            row = cfg.data["agents"]["list"][0]
            self.assertEqual(row.get("customMeta"), {"x": 1})
            self.assertEqual(row.get("notes"), "keep-me")
            self.assertEqual(row.get("model"), {"primary": "openrouter/openrouter/free", "fallbacks": []})
            self.assertNotIn("security", row)

    def test_validate_workspace_path_relaxed_workspace_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _DummyConfig(os.path.join(tmp, "workspace"))
            with patch.object(routing, "config", cfg):
                self.assertTrue(routing._validate_workspace_path(os.path.join(tmp, "workspace_data")))
                self.assertFalse(routing._validate_workspace_path(os.path.join(tmp, "data_workspace")))

    def test_detect_existing_workspace_prefers_default_and_skips_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "workspace"), exist_ok=True)
            os.makedirs(os.path.join(tmp, "workspace_01"), exist_ok=True)
            cfg = _DummyConfig(os.path.join(tmp, "workspace"))
            with patch.object(routing, "config", cfg):
                got = routing._detect_existing_workspace(cfg.data["agents"]["list"])
                self.assertEqual(got, os.path.join(tmp, "workspace"))

            cfg.data["agents"]["list"] = [{"id": "main", "workspace": os.path.join(tmp, "workspace")}]
            with patch.object(routing, "config", cfg):
                got = routing._detect_existing_workspace(cfg.data["agents"]["list"])
                self.assertEqual(got, os.path.join(tmp, "workspace_01"))

    def test_validate_existing_workspace_requires_existing_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _DummyConfig(os.path.join(tmp, "workspace"))
            ws = os.path.join(tmp, "workspace")
            os.makedirs(ws, exist_ok=True)
            with patch.object(routing, "config", cfg):
                ok1, _ = routing._validate_existing_workspace(ws)
                self.assertFalse(ok1)
                with open(os.path.join(ws, "AGENTS.md"), "w", encoding="utf-8") as f:
                    f.write("# a")
                with open(os.path.join(ws, "SOUL.md"), "w", encoding="utf-8") as f:
                    f.write("# s")
                ok2, _ = routing._validate_existing_workspace(ws)
                self.assertTrue(ok2)

    def test_set_agent_control_plane_whitelist_enable_disable(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _DummyConfig(os.path.join(tmp, "workspace"))
            cfg.data["agents"]["list"] = [
                {
                    "id": "main",
                    "workspace": os.path.join(tmp, "workspace"),
                    "model": {"primary": "openrouter/openrouter/free"},
                    "subagents": {"allowAgents": ["*"]},
                    "security": {"workspaceScope": "workspace-only", "controlPlaneCapabilities": []},
                }
            ]
            with patch.object(routing, "config", cfg):
                ok1 = routing.set_agent_control_plane_whitelist(
                    "main", True, routing.RECOMMENDED_CONTROL_PLANE_CAPABILITIES
                )
                self.assertTrue(ok1)
                caps = cfg.data["agents"]["list"][0]["security"]["controlPlaneCapabilities"]
                self.assertIn("model.switch", caps)
                ok2 = routing.set_agent_control_plane_whitelist("main", False, [])
                self.assertTrue(ok2)
                caps2 = cfg.data["agents"]["list"][0]["security"]["controlPlaneCapabilities"]
                self.assertEqual(caps2, [])

    def test_set_agent_model_policy_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _DummyConfig(os.path.join(tmp, "workspace"))
            cfg.data["agents"]["list"] = [{"id": "main", "workspace": os.path.join(tmp, "workspace")}]
            with patch.object(routing, "config", cfg):
                ok1 = routing.set_agent_model_policy(
                    "main",
                    "openrouter/openrouter/free",
                    "openrouter/qwen/qwen3-coder:free",
                )
                self.assertTrue(ok1)
                model = cfg.data["agents"]["list"][0].get("model")
                self.assertIsInstance(model, dict)
                self.assertEqual(model.get("primary"), "openrouter/openrouter/free")
                ok2 = routing.clear_agent_model_policy("main")
                self.assertTrue(ok2)
                self.assertTrue("model" not in cfg.data["agents"]["list"][0])

    def test_spawn_model_policy_set_and_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _DummyConfig(os.path.join(tmp, "workspace"))
            cfg.data["agents"]["defaults"] = {"workspace": os.path.join(tmp, "workspace"), "subagents": {"maxConcurrent": 8}}
            with patch.object(routing, "config", cfg):
                ok = routing.set_spawn_model_policy(
                    "openrouter/openrouter/free",
                    "openrouter/qwen/qwen3-coder:free",
                )
                self.assertTrue(ok)
                p, f = routing.get_spawn_model_policy()
                self.assertEqual(p, "openrouter/openrouter/free")
                self.assertEqual(f, ["openrouter/qwen/qwen3-coder:free"])

    def test_list_agent_model_overrides(self):
        cfg = _DummyConfig("/root/.openclaw/workspace")
        cfg.data["agents"]["list"] = [
            {"id": "main", "workspace": "/root/.openclaw/workspace", "model": "openrouter/openrouter/free"},
            {"id": "worker", "workspace": "/root/.openclaw/workspace_01"},
        ]
        with patch.object(routing, "config", cfg):
            overrides = routing.list_agent_model_overrides()
        self.assertEqual(overrides, ["main"])

    def test_list_agent_model_override_details(self):
        cfg = _DummyConfig("/root/.openclaw/workspace")
        cfg.data["agents"]["list"] = [
            {
                "id": "main",
                "workspace": "/root/.openclaw/workspace",
                "model": {"primary": "openrouter/openrouter/free", "fallbacks": ["openrouter/qwen/qwen3-coder:free"]},
            },
            {"id": "worker", "workspace": "/root/.openclaw/workspace_01"},
        ]
        with patch.object(routing, "config", cfg):
            details = routing.list_agent_model_override_details()
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["agent_id"], "main")
        self.assertEqual(details[0]["primary"], "openrouter/openrouter/free")
        self.assertEqual(details[0]["fallbacks"], ["openrouter/qwen/qwen3-coder:free"])


if __name__ == "__main__":
    unittest.main()
