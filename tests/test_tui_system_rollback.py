import os
import tempfile
import unittest
from unittest.mock import patch

from tui import system


class TuiSystemRollbackTest(unittest.TestCase):
    def test_list_config_backups_supports_new_and_legacy_names(self):
        with tempfile.TemporaryDirectory() as td:
            easy = os.path.join(td, "easyclaw_20260227_100000.json.bak")
            legacy = os.path.join(td, "openclaw_bkp_20260227_090000.json")
            with open(easy, "w", encoding="utf-8") as f:
                f.write("{}")
            with open(legacy, "w", encoding="utf-8") as f:
                f.write("{}")
            with patch.object(system, "DEFAULT_BACKUP_DIR", td):
                files = system._list_config_backups(limit=10)
            names = [os.path.basename(x) for x in files]
            self.assertIn("easyclaw_20260227_100000.json.bak", names)
            self.assertIn("openclaw_bkp_20260227_090000.json", names)

    def test_rollback_config_restores_selected_file(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = os.path.join(td, "openclaw.json")
            bkp = os.path.join(td, "easyclaw_20260227_100000.json.bak")
            pre = os.path.join(td, "easyclaw_pre.json.bak")
            with open(cfg, "w", encoding="utf-8") as f:
                f.write("{\"v\":\"before\"}")
            with open(bkp, "w", encoding="utf-8") as f:
                f.write("{\"v\":\"after\"}")

            with patch.object(system, "DEFAULT_BACKUP_DIR", td), patch.object(system, "DEFAULT_CONFIG_PATH", cfg), patch(
                "tui.system.Prompt.ask", side_effect=["1"]
            ), patch("tui.system.Confirm.ask", return_value=True), patch("tui.system.pause_enter", return_value=None), patch.object(
                system.config, "backup", return_value=pre
            ):
                system.rollback_config()

            with open(cfg, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("\"after\"", content)


if __name__ == "__main__":
    unittest.main()
