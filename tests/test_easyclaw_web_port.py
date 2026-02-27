import os
import unittest
from unittest.mock import patch

import easyclaw


class EasyClawWebPortTest(unittest.TestCase):
    @patch("easyclaw._start_web_server")
    def test_web_default_port_is_4231(self, mock_start):
        with patch.dict(os.environ, {}, clear=False):
            easyclaw.main(["easyclaw.py", "web"])
        self.assertEqual(mock_start.call_args.kwargs.get("port"), 4231)

    @patch("easyclaw._start_web_server")
    def test_web_port_can_be_overridden_by_env(self, mock_start):
        with patch.dict(os.environ, {"EASYCLAW_WEB_PORT": "5123"}, clear=False):
            easyclaw.main(["easyclaw.py", "web"])
        self.assertEqual(mock_start.call_args.kwargs.get("port"), 5123)

    @patch("easyclaw._start_web_server")
    def test_web_port_can_be_overridden_by_flag(self, mock_start):
        with patch.dict(os.environ, {"EASYCLAW_WEB_PORT": "5123"}, clear=False):
            easyclaw.main(["easyclaw.py", "web", "--port", "6123"])
        self.assertEqual(mock_start.call_args.kwargs.get("port"), 6123)


if __name__ == "__main__":
    unittest.main()
