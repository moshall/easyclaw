import unittest
from unittest.mock import patch

import core


class TestSubagentGlobal(unittest.TestCase):
    @patch("core.run_cli")
    def test_update_subagent_global_targets_main_agent_index(self, mock_run_cli):
        mock_run_cli.return_value = ("", "", 0)
        cfg = core.OpenClawConfig(path="/tmp/nonexistent-openclaw.json")
        cfg.data = {
            "agents": {
                "list": [
                    {"id": "worker", "subagents": {"allowAgents": []}},
                    {"id": "main", "subagents": {"allowAgents": []}},
                ],
                "defaults": {"subagents": {"maxConcurrent": 8}},
            }
        }

        ok = cfg.update_subagent_global(allow_agents=["*"])
        self.assertTrue(ok)
        called = mock_run_cli.call_args_list[0].args[0]
        self.assertEqual(called[0:3], ["config", "set", "agents.list[1].subagents.allowAgents"])

    @patch("core.run_cli")
    def test_update_subagent_global_fallbacks_to_first_when_main_missing(self, mock_run_cli):
        mock_run_cli.return_value = ("", "", 0)
        cfg = core.OpenClawConfig(path="/tmp/nonexistent-openclaw.json")
        cfg.data = {
            "agents": {
                "list": [{"id": "worker", "subagents": {"allowAgents": []}}],
                "defaults": {"subagents": {"maxConcurrent": 8}},
            }
        }

        ok = cfg.update_subagent_global(allow_agents=["*"])
        self.assertTrue(ok)
        called = mock_run_cli.call_args_list[0].args[0]
        self.assertEqual(called[0:3], ["config", "set", "agents.list[0].subagents.allowAgents"])

    @patch("core.run_cli")
    def test_update_subagent_global_fallback_creates_main_when_agents_list_empty(self, mock_run_cli):
        # CLI path 写入失败（典型：agents.list 不存在）
        mock_run_cli.return_value = ("", "Config path not found", 1)
        cfg = core.OpenClawConfig(path="/tmp/nonexistent-openclaw.json")
        cfg.data = {"agents": {"defaults": {"subagents": {"maxConcurrent": 8}}}}

        with patch.object(cfg, "save", return_value=True), patch.object(cfg, "reload", return_value=None):
            ok = cfg.update_subagent_global(allow_agents=["*"])

        self.assertTrue(ok)
        agents_list = cfg.data.get("agents", {}).get("list", [])
        self.assertEqual(len(agents_list), 1)
        self.assertEqual(agents_list[0].get("id"), "main")
        self.assertEqual(agents_list[0].get("subagents", {}).get("allowAgents"), ["*"])


if __name__ == "__main__":
    unittest.main()
