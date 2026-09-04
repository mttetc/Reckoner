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

    # Agent (SPEC § 9). Providers:
    #   openai_compat — any OpenAI-compatible chat API with tool calling: Ollama (free, local,
    #                   default), Groq / Mistral / OpenRouter / Gemini free tiers, …
    #   anthropic     — Claude via the Anthropic API (needs anthropic_api_key)
    #   scripted      — no model: deterministic policy for tests/CI, labelled as such
    # If the configured provider cannot be reached at startup, the scripted policy answers and
    # says so; nothing is ever silently approximated.
    llm: str = "openai_compat"
    llm_model: str = "qwen2.5:7b"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str | None = Field(default=None, validation_alias="RECKONER_LLM_API_KEY")
    anthropic_api_key: str | None = Field(
        default=None, validation_alias="RECKONER_ANTHROPIC_API_KEY"
    )
    agent_max_steps: int = 6

    # World of Warcraft (Retail) engine: SimulationCraft CLI. Unset → recalculation unavailable.
    simc_bin: str | None = None
    simc_iterations: int = 1000
    wowsims_bin: str | None = None  # wowsimcli (WoW Classic engine), built with the item database
    wowsims_iterations: int = 1000
    wowsims_src: str | None = (
        None  # WoWSims checkout for db.json and talent trees (default: next to the CLI)
    )


settings = Settings()
