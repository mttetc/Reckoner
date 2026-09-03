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


settings = Settings()
