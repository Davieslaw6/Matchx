from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

# Competition code -> display name. Add leagues here (or via ENABLED_LEAGUES) to enable more.
KNOWN_LEAGUES = {
    "PL": "Premier League",
    "PD": "La Liga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./footy.db"
    auto_create_tables: bool = False   # False: schema is managed by `alembic upgrade head`
    football_data_api_key: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"
    data_provider: str = "football-data.org"      # default; can be switched at runtime (stored in DB)
    api_football_api_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    llm_provider: str = "anthropic"               # anthropic | openai (any OpenAI-compatible endpoint)
    llm_api_key: str = ""
    llm_base_url: str = ""                        # optional override
    llm_model: str = "claude-sonnet-5-5"
    llm_timeout_s: float = 60.0
    access_token: str = ""            # if empty, only localhost may call the API
    enabled_leagues: str = "PL,PD,SA,BL1,FL1"
    http_timeout_s: float = 10.0
    max_retries: int = 2
    cache_ttl_s: int = 300
    min_seconds_between_requests: float = 6.5   # free tier: 10 calls/min
    half_life_days: float = 365.0
    stale_after_hours: int = 48

    @property
    def leagues(self) -> list[str]:
        return [c.strip().upper() for c in self.enabled_leagues.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
