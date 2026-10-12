from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    app_name: str = "MATCH X"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    allowed_origin: str = "http://localhost:3000"
    database_url: str = "sqlite+aiosqlite:///./matchx-dev.db"
    owner_exists: bool = False
    demo_mode: bool = False
    timezone: str = "Africa/Lagos"
    session_secret: SecretStr = SecretStr("development-only-change-me")  # nosec B105: rejected in production
    provider_api_key: SecretStr | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str = "gpt-5-mini"
    llm_base_url: str = "https://api.openai.com/v1"

    def validate_public_bind(self) -> None:
        public_bind = self.host not in {"127.0.0.1", "::1", "localhost"}
        if public_bind and not self.owner_exists:
            raise RuntimeError("Refusing public-interface startup without an owner. Provision an owner first.")
        if self.environment == "production" and self.session_secret.get_secret_value() == "development-only-change-me":
            raise RuntimeError("SESSION_SECRET must be set to a strong secret in production.")

@lru_cache
def get_settings() -> Settings:
    return Settings()
