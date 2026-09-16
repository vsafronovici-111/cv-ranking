from __future__ import annotations

import logging
import unittest

from cv_ranker.config import LocalLoggingSettings, ProdLoggingSettings
from cv_ranker.logging_config import configure_logging


class LoggingConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._root_handlers = logging.getLogger().handlers[:]
        self._root_level = logging.getLogger().level

    def tearDown(self) -> None:
        root = logging.getLogger()
        root.handlers[:] = self._root_handlers
        root.setLevel(self._root_level)

    def test_load_logging_settings_defaults_local_to_debug(self) -> None:
        # `_env_file=None` bypasses the developer's real (gitignored)
        # `config/local.env` so this checks the class's declared default,
        # not whatever level happens to be configured on this machine.
        self.assertEqual(LocalLoggingSettings(_env_file=None).level, "DEBUG")

    def test_load_logging_settings_defaults_prod_to_info(self) -> None:
        self.assertEqual(ProdLoggingSettings(_env_file=None).level, "INFO")

    def test_configure_logging_applies_resolved_level(self) -> None:
        logging.getLogger().handlers.clear()

        configure_logging("prod")

        self.assertEqual(logging.getLogger().level, logging.INFO)


if __name__ == "__main__":
    unittest.main()
