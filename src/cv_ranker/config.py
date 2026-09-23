from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: src/cv_ranker/config.py -> src/cv_ranker -> src -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = _REPO_ROOT / "config"

# Shared local-dev defaults, plus an optional personal override file (not
# tracked in git, silently skipped if absent) that wins on any key it sets —
# same layering as this repo's own .claude/settings.json +
# .claude/settings.local.json.
_LOCAL_ENV_FILES = (str(_CONFIG_DIR / "local.env"), str(_CONFIG_DIR / "local.env.local"))


class LLMSettings(BaseSettings):
    """Resolved LLM connection settings for a given environment.

    Values are resolved by pydantic-settings in this priority order:
    1. Explicit constructor kwargs (not used here)
    2. Environment variables (e.g. `CV_RANKER_BASE_URL`)
    3. The matching `config/<env>.env` dotenv file, if present
    4. The field defaults declared on the subclass below
    """

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str
    api_key: str
    model: str
    timeout_seconds: int


class LocalLLMSettings(LLMSettings):
    """Local development defaults: Ollama's OpenAI-compatible API at /v1.

    https://github.com/ollama/ollama/blob/main/docs/openai.md
    """

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_",
        env_file=_LOCAL_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"  # Ollama ignores the key; the OpenAI SDK requires a non-empty value.
    model: str = "qwen3:14b"
    timeout_seconds: int = 150


class ProdLLMSettings(LLMSettings):
    """Production defaults: vLLM's OpenAI-compatible server.

    https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
    """

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_",
        env_file=str(_CONFIG_DIR / "prod.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    model: str = "Qwen/Qwen3-14B"
    timeout_seconds: int = 120


class DBSettingsBase(BaseSettings):
    """Resolved Postgres connection settings for a given environment."""

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_DB_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    dsn: str = "postgresql://postgres:postgres@localhost:5432/cvranker"


class LocalDBSettings(DBSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_DB_",
        env_file=_LOCAL_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ProdDBSettings(DBSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_DB_",
        env_file=str(_CONFIG_DIR / "prod.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


_DB_SETTINGS_CLASS_BY_ENV: dict[str, type[DBSettingsBase]] = {
    "local": LocalDBSettings,
    "prod": ProdDBSettings,
}


class QdrantSettingsBase(BaseSettings):
    """Resolved Qdrant connection settings for a given environment.

    Qdrant's API key (when set) protects BOTH the REST/HTTP interface and
    the gRPC interface — it's a single service-level secret, not one per
    protocol. See `docker/docker-compose.yml`'s `QDRANT__SERVICE__API_KEY`.
    """

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_QDRANT_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "http://localhost:6333"
    api_key: str = ""


class LocalQdrantSettings(QdrantSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_QDRANT_",
        env_file=_LOCAL_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ProdQdrantSettings(QdrantSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_QDRANT_",
        env_file=str(_CONFIG_DIR / "prod.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


_QDRANT_SETTINGS_CLASS_BY_ENV: dict[str, type[QdrantSettingsBase]] = {
    "local": LocalQdrantSettings,
    "prod": ProdQdrantSettings,
}


class EmbeddingSettingsBase(BaseSettings):
    """Resolved embedding-model connection settings for a given environment.

    Uses the OpenAI-compatible `/v1/embeddings` endpoint, same as
    `LLMSettings` — both Ollama and vLLM serve embeddings through it, so
    `cv_ranker.embedding_client.EmbeddingClient` works against either backend
    unchanged.
    """

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_EMBEDDING_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 90


class LocalEmbeddingSettings(EmbeddingSettingsBase):
    """Local development defaults: Ollama's OpenAI-compatible API at /v1."""

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_EMBEDDING_",
        env_file=_LOCAL_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"  # Ollama ignores the key; the OpenAI SDK requires a non-empty value.
    model: str = "qwen3-embedding:4b"
    timeout_seconds: int = 90


class ProdEmbeddingSettings(EmbeddingSettingsBase):
    """Production defaults: vLLM's OpenAI-compatible server."""

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_EMBEDDING_",
        env_file=str(_CONFIG_DIR / "prod.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    model: str = "Qwen/Qwen3-Embedding-4B"
    timeout_seconds: int = 90


_EMBEDDING_SETTINGS_CLASS_BY_ENV: dict[str, type[EmbeddingSettingsBase]] = {
    "local": LocalEmbeddingSettings,
    "prod": ProdEmbeddingSettings,
}


class LoggingSettingsBase(BaseSettings):
    """Resolved logging settings for a given environment."""

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_LOG_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    level: str = "INFO"


class LocalLoggingSettings(LoggingSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_LOG_",
        env_file=_LOCAL_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    level: str = "DEBUG"


class ProdLoggingSettings(LoggingSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_LOG_",
        env_file=str(_CONFIG_DIR / "prod.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    level: str = "INFO"


_LOGGING_SETTINGS_CLASS_BY_ENV: dict[str, type[LoggingSettingsBase]] = {
    "local": LocalLoggingSettings,
    "prod": ProdLoggingSettings,
}


class KafkaSettingsBase(BaseSettings):
    """Resolved Kafka connection settings for a given environment."""

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_KAFKA_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bootstrap_servers: str = "localhost:9092"


class LocalKafkaSettings(KafkaSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_KAFKA_",
        env_file=_LOCAL_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ProdKafkaSettings(KafkaSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_KAFKA_",
        env_file=str(_CONFIG_DIR / "prod.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


_KAFKA_SETTINGS_CLASS_BY_ENV: dict[str, type[KafkaSettingsBase]] = {
    "local": LocalKafkaSettings,
    "prod": ProdKafkaSettings,
}


class RedisSettingsBase(BaseSettings):
    """Resolved Redis connection settings for a given environment."""

    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_REDIS_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "redis://localhost:6379"


class LocalRedisSettings(RedisSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_REDIS_",
        env_file=_LOCAL_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ProdRedisSettings(RedisSettingsBase):
    model_config = SettingsConfigDict(
        env_prefix="CV_RANKER_REDIS_",
        env_file=str(_CONFIG_DIR / "prod.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


_REDIS_SETTINGS_CLASS_BY_ENV: dict[str, type[RedisSettingsBase]] = {
    "local": LocalRedisSettings,
    "prod": ProdRedisSettings,
}


_SETTINGS_CLASS_BY_ENV: dict[str, type[LLMSettings]] = {
    "local": LocalLLMSettings,
    "prod": ProdLLMSettings,
}


def load_llm_settings(env_name: str | None = None) -> LLMSettings:
    """Resolve LLM settings for the requested environment.

    Resolution order for which environment to use:
    1. Explicit `env_name` argument (e.g., from a CLI flag)
    2. `CV_RANKER_ENV` environment variable
    3. Falls back to "local"

    For the chosen environment, individual fields can still be overridden via:
    - CV_RANKER_BASE_URL
    - CV_RANKER_API_KEY
    - CV_RANKER_MODEL
    - CV_RANKER_TIMEOUT_SECONDS

    ...or by editing `config/local.env` / `config/prod.env` (see the
    `.env.example` templates in `config/`).

    This lets you keep `local` as the safe default for everyday development
    (pointing at Ollama) while switching to `prod` (vLLM) via config/env vars
    without touching application code.
    """
    resolved_env = (env_name or os.environ.get("CV_RANKER_ENV") or "local").strip().lower()

    settings_cls = _SETTINGS_CLASS_BY_ENV.get(resolved_env)
    if settings_cls is None:
        valid = ", ".join(sorted(_SETTINGS_CLASS_BY_ENV))
        raise ValueError(f"Unknown environment '{resolved_env}'. Expected one of: {valid}.")

    return settings_cls()


def load_db_settings(env_name: str | None = None) -> DBSettingsBase:
    """Resolve the Postgres DSN for the requested environment.

    Same resolution order as `load_llm_settings`: explicit arg ->
    `CV_RANKER_ENV` -> "local". The DSN itself can be overridden via
    `CV_RANKER_DB_DSN` or `config/<env>.env`.
    """
    resolved_env = (env_name or os.environ.get("CV_RANKER_ENV") or "local").strip().lower()

    settings_cls = _DB_SETTINGS_CLASS_BY_ENV.get(resolved_env)
    if settings_cls is None:
        valid = ", ".join(sorted(_DB_SETTINGS_CLASS_BY_ENV))
        raise ValueError(f"Unknown environment '{resolved_env}'. Expected one of: {valid}.")

    return settings_cls()


def load_qdrant_settings(env_name: str | None = None) -> QdrantSettingsBase:
    """Resolve Qdrant connection settings for the requested environment.

    Same resolution order as `load_db_settings`: explicit arg ->
    `CV_RANKER_ENV` -> "local". `url`/`api_key` can be overridden via
    `CV_RANKER_QDRANT_URL` / `CV_RANKER_QDRANT_API_KEY` or `config/<env>.env`.
    """
    resolved_env = (env_name or os.environ.get("CV_RANKER_ENV") or "local").strip().lower()

    settings_cls = _QDRANT_SETTINGS_CLASS_BY_ENV.get(resolved_env)
    if settings_cls is None:
        valid = ", ".join(sorted(_QDRANT_SETTINGS_CLASS_BY_ENV))
        raise ValueError(f"Unknown environment '{resolved_env}'. Expected one of: {valid}.")

    return settings_cls()


def load_embedding_settings(env_name: str | None = None) -> EmbeddingSettingsBase:
    """Resolve embedding-model connection settings for the requested environment.

    Same resolution order as `load_db_settings`: explicit arg ->
    `CV_RANKER_ENV` -> "local". `base_url`/`api_key`/`model`/`timeout_seconds`
    can be overridden via `CV_RANKER_EMBEDDING_BASE_URL` /
    `CV_RANKER_EMBEDDING_API_KEY` / `CV_RANKER_EMBEDDING_MODEL` /
    `CV_RANKER_EMBEDDING_TIMEOUT_SECONDS` or `config/<env>.env`.
    """
    resolved_env = (env_name or os.environ.get("CV_RANKER_ENV") or "local").strip().lower()

    settings_cls = _EMBEDDING_SETTINGS_CLASS_BY_ENV.get(resolved_env)
    if settings_cls is None:
        valid = ", ".join(sorted(_EMBEDDING_SETTINGS_CLASS_BY_ENV))
        raise ValueError(f"Unknown environment '{resolved_env}'. Expected one of: {valid}.")

    return settings_cls()


def load_logging_settings(env_name: str | None = None) -> LoggingSettingsBase:
    """Resolve logging settings for the requested environment.

    Same resolution order as `load_db_settings`: explicit arg ->
    `CV_RANKER_ENV` -> "local". `level` can be overridden via
    `CV_RANKER_LOG_LEVEL` or `config/<env>.env`. Defaults to `DEBUG` locally
    and `INFO` in prod.
    """
    resolved_env = (env_name or os.environ.get("CV_RANKER_ENV") or "local").strip().lower()

    settings_cls = _LOGGING_SETTINGS_CLASS_BY_ENV.get(resolved_env)
    if settings_cls is None:
        valid = ", ".join(sorted(_LOGGING_SETTINGS_CLASS_BY_ENV))
        raise ValueError(f"Unknown environment '{resolved_env}'. Expected one of: {valid}.")

    return settings_cls()


def load_kafka_settings(env_name: str | None = None) -> KafkaSettingsBase:
    """Resolve Kafka connection settings for the requested environment.

    Same resolution order as `load_db_settings`: explicit arg ->
    `CV_RANKER_ENV` -> "local". `bootstrap_servers` can be overridden via
    `CV_RANKER_KAFKA_BOOTSTRAP_SERVERS` or `config/<env>.env`.
    """
    resolved_env = (env_name or os.environ.get("CV_RANKER_ENV") or "local").strip().lower()

    settings_cls = _KAFKA_SETTINGS_CLASS_BY_ENV.get(resolved_env)
    if settings_cls is None:
        valid = ", ".join(sorted(_KAFKA_SETTINGS_CLASS_BY_ENV))
        raise ValueError(f"Unknown environment '{resolved_env}'. Expected one of: {valid}.")

    return settings_cls()


def load_redis_settings(env_name: str | None = None) -> RedisSettingsBase:
    """Resolve Redis connection settings for the requested environment.

    Same resolution order as `load_db_settings`: explicit arg ->
    `CV_RANKER_ENV` -> "local". `url` can be overridden via
    `CV_RANKER_REDIS_URL` or `config/<env>.env`.
    """
    resolved_env = (env_name or os.environ.get("CV_RANKER_ENV") or "local").strip().lower()

    settings_cls = _REDIS_SETTINGS_CLASS_BY_ENV.get(resolved_env)
    if settings_cls is None:
        valid = ", ".join(sorted(_REDIS_SETTINGS_CLASS_BY_ENV))
        raise ValueError(f"Unknown environment '{resolved_env}'. Expected one of: {valid}.")

    return settings_cls()
