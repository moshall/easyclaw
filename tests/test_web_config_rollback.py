import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from web import app as web_app


class WebConfigRollbackTest(unittest.TestCase):
    def test_list_and_resolve_backups_support_multiple_formats(self):
        with tempfile.TemporaryDirectory() as td:
            easy = os.path.join(td, "easyclaw_20260227_100000.json.bak")
            old = os.path.join(td, "openclaw_bkp_20260227_090000.json")
            with open(easy, "w", encoding="utf-8") as f:
                f.write("{\"v\":1}")
            with open(old, "w", encoding="utf-8") as f:
                f.write("{\"v\":0}")

            with patch.object(web_app, "DEFAULT_BACKUP_DIR", td):
                items = web_app._list_config_backups(limit=10)
                names = [x.get("name") for x in items]
                self.assertIn("easyclaw_20260227_100000.json.bak", names)
                self.assertIn("openclaw_bkp_20260227_090000.json", names)

                resolved = web_app._resolve_backup_file_by_name("easyclaw_20260227_100000.json.bak")
                self.assertEqual(os.path.abspath(easy), resolved)

    def test_rollback_api_copies_backup_to_config(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = os.path.join(td, "openclaw.json")
            bkp = os.path.join(td, "easyclaw_20260227_100000.json.bak")
            pre = os.path.join(td, "easyclaw_pre.json.bak")

            with open(cfg, "w", encoding="utf-8") as f:
                f.write("{\"model\":\"before\"}")
            with open(bkp, "w", encoding="utf-8") as f:
                f.write("{\"model\":\"after\"}")
            with open(pre, "w", encoding="utf-8") as f:
                f.write("{\"model\":\"pre\"}")

            with patch.object(web_app, "DEFAULT_BACKUP_DIR", td), patch.object(web_app, "DEFAULT_CONFIG_PATH", cfg), patch.object(
                web_app.config, "backup", return_value=pre
            ), patch.object(web_app.config, "reload", return_value=None), patch.object(web_app, "_invalidate_cache", return_value=None), patch.object(
                web_app, "_state_payload", return_value={}
            ):
                body = web_app.ConfigRollbackIn(backupName=os.path.basename(bkp))
                out = asyncio.run(web_app.rollback_config_api(body))

            with open(cfg, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("\"after\"", content)
            self.assertEqual(out.get("restored"), os.path.basename(bkp))
            self.assertEqual(out.get("preBackupPath"), pre)


if __name__ == "__main__":
    unittest.main()
