from __future__ import annotations

from cv_ranker.config import load_db_settings
from cv_ranker.db import CVStore, DBSettings


def get_store() -> CVStore:
    return CVStore(DBSettings(dsn=load_db_settings().dsn))
