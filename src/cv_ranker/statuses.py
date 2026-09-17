from __future__ import annotations

from enum import StrEnum


class CVStatus(StrEnum):
    """Lifecycle states for a row in the `cvs` table."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class MessageResponseStatus(StrEnum):
    """Lifecycle states for a row in the `message_responses` table."""

    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
