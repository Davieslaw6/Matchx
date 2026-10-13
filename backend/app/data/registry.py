"""Provider registry + runtime selection (stored in app_settings)."""
from sqlalchemy.orm import Session
from ..config import Settings
from ..db import utcnow
from ..models import AppSetting
from .provider import ApiFootballClient, FootballDataOrgClient, ProviderError

PROVIDER_NAMES = ["football-data.org", "api-football"]


def is_configured(name: str, cfg: Settings) -> bool:
    return bool({"football-data.org": cfg.football_data_api_key, "api-football": cfg.api_football_api_key}.get(name))


def build_provider(name: str, cfg: Settings, **kw):
    common = dict(timeout_s=cfg.http_timeout_s, max_retries=cfg.max_retries, cache_ttl_s=cfg.cache_ttl_s,
                  min_interval_s=cfg.min_seconds_between_requests, **kw)
    if name == "football-data.org":
        return FootballDataOrgClient(cfg.football_data_api_key, cfg.football_data_base_url, **common)
    if name == "api-football":
        return ApiFootballClient(cfg.api_football_api_key, cfg.api_football_base_url, **common)
    raise ProviderError(f"Unknown provider '{name}'")


def get_active_provider_name(s: Session, cfg: Settings) -> str:
    row = s.get(AppSetting, "provider")
    return row.value if row and row.value in PROVIDER_NAMES else cfg.data_provider


def set_active_provider(s: Session, name: str) -> None:
    if name not in PROVIDER_NAMES:
        raise ProviderError(f"Unknown provider '{name}'")
    row = s.get(AppSetting, "provider")
    now = utcnow()
    if row: row.value, row.updated_at = name, now
    else: s.add(AppSetting(key="provider", value=name, updated_at=now))
    s.commit()
