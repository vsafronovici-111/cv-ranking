from __future__ import annotations

import logging

from cv_ranker.config import load_logging_settings


def configure_logging(env_name: str | None = None) -> None:
    """Configure the root logger's level from the resolved logging settings.

    Call once at process startup (CLI or API). Emits to stderr via
    `logging.basicConfig` for now; centralizing log shipping in production
    later (e.g. to a log aggregator) only needs to change this one function,
    not every call site.
    """
    level = load_logging_settings(env_name).level
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
