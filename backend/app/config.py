from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECKONER_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://reckoner:reckoner@localhost:5432/reckoner"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_code_bytes: int = 512 * 1024

    # Headless Path of Building engine (SPEC § 5 B). Unset → recalculation is honestly unavailable.
    pob_src: Path | None = Field(
        default=None,
        description="Path of Building checkout `src/` directory (see scripts/install_pob.sh).",
    )
    pob_source_commit: str | None = Field(
        default=None, description="Commit of that checkout; recorded in provenance when known."
    )
    luajit_bin: str = "luajit"
    engine_timeout_s: float = 90.0

    # Corpus ingestion (SPEC § 7). Identify the fetcher; sources ask for contact info.
    corpus_user_agent: str = (
        "Reckoner/0.1 (+https://github.com/mttetc/Reckoner; contact: GitHub issues)"
    )
    corpus_request_delay_s: float = 2.0

    # Knowledge embeddings (SPEC § 6). "auto" = local fastembed model if installed, else hash.
    # "hash" = dependency-free deterministic embedder (tests / CI).
    embedder: str = "auto"


settings = Settings()
