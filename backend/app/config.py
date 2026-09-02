from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECKONER_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://reckoner:reckoner@localhost:5432/reckoner"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_code_bytes: int = 512 * 1024


settings = Settings()
