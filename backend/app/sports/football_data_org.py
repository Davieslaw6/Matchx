"""football-data.org v4 adapter. Only returns provider-sourced, validated records."""
from datetime import date, datetime, timezone
import asyncio
import random
from datetime import timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.sports.provider import CapabilityFlags, Unsupported

class ProviderError(RuntimeError):
    """Provider request or payload could not be safely used."""

class CompetitionRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    code: str | None = None
    name: str
    area: dict[str, Any] = Field(default_factory=dict)
    currentSeason: dict[str, Any] | None = None

class TeamRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str
    shortName: str | None = None
    tla: str | None = None
    area: dict[str, Any] = Field(default_factory=dict)

class MatchRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    utcDate: datetime
    status: str
    matchday: int | None = None
    season: dict[str, Any] = Field(default_factory=dict)
    competition: dict[str, Any] = Field(default_factory=dict)
    homeTeam: dict[str, Any]
    awayTeam: dict[str, Any]
    score: dict[str, Any] = Field(default_factory=dict)
    venue: str | None = None

class FootballDataOrgProvider:
    name = "football-data.org"
    capabilities = CapabilityFlags(supports_odds=False, supports_xg=False,
                                   supports_injuries=False, supports_cards=False,
                                   supports_corners=False)

    def __init__(self, api_key: str, *, base_url: str = "https://api.football-data.org/v4",
                 timeout_seconds: float = 12, max_retries: int = 3,
                 client: httpx.AsyncClient | None = None):
        if not api_key.strip():
            raise ValueError("football-data.org API token is required.")
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max(0, min(max_retries, 5))
        self._client = client
        self._owns_client = client is None
        self._failure_count = 0
        self._open_until: datetime | None = None

    async def __aenter__(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_):
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if self._open_until and now < self._open_until:
            raise ProviderError("Provider circuit is open after repeated failures.")
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(
                    f"{self._base_url}/{path.lstrip('/')}",
                    params=params,
                    headers={"X-Auth-Token": self._api_key, "Accept": "application/json"},
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt >= self._max_retries:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    delay = min(30.0, 0.5 * (2 ** attempt) + random.uniform(0, 0.35))
                    if retry_after:
                        try:
                            delay = max(0.0, min(30.0, float(retry_after)))
                        except ValueError:
                            try:
                                retry_date = parsedate_to_datetime(retry_after)
                                delay = max(0.0, min(30.0, (retry_date - datetime.now(timezone.utc)).total_seconds()))
                            except (TypeError, ValueError, OverflowError):
                                pass
                    await asyncio.sleep(delay)
                    continue
                if response.is_error:
                    raise ProviderError(f"Provider returned HTTP {response.status_code}.")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ProviderError("Provider returned a non-object JSON payload.")
                self._failure_count = 0
                self._open_until = None
                return payload
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ValueError) as exc:
                last_error = exc
                self._failure_count += 1
                if self._failure_count >= 5:
                    # Short circuit cooldown is deliberately bounded; next request can retry later.
                    self._open_until = datetime.now(timezone.utc) + timedelta(seconds=30)
                if attempt < self._max_retries:
                    await asyncio.sleep(min(8.0, 0.35 * (2 ** attempt) + random.uniform(0, 0.2)))
        raise ProviderError(f"Provider request failed after bounded retries: {type(last_error).__name__ if last_error else 'unknown'}") from last_error

    async def competitions(self) -> list[dict[str, Any]]:
        payload = await self._get("competitions")
        raw = payload.get("competitions")
        if not isinstance(raw, list):
            raise ProviderError("Missing competitions array in provider response.")
        try:
            return [{"provider_id": str(x.id), "code": x.code, "name": x.name,
                     "country": x.area.get("name"), "season": str((x.currentSeason or {}).get("id", "")) or None}
                    for item in raw if (x := CompetitionRecord.model_validate(item))]
        except (ValidationError, TypeError) as exc:
            raise ProviderError("Invalid competition record in provider response.") from exc

    @staticmethod
    def _validate_path_id(value: str, field: str) -> str:
        if not value or len(value) > 80 or not all(char.isalnum() or char in "-_" for char in value):
            raise ValueError(f"Invalid {field}.")
        return value

    async def teams(self, competition_id: str) -> list[dict[str, Any]]:
        competition_id = self._validate_path_id(competition_id, "competition id")
        payload = await self._get(f"competitions/{competition_id}/teams")
        raw = payload.get("teams")
        if not isinstance(raw, list):
            raise ProviderError("Missing teams array in provider response.")
        try:
            return [{"provider_id": str(x.id), "name": x.name, "short_name": x.shortName,
                     "tla": x.tla, "country": x.area.get("name")}
                    for item in raw if (x := TeamRecord.model_validate(item))]
        except (ValidationError, TypeError) as exc:
            raise ProviderError("Invalid team record in provider response.") from exc

    async def _matches(self, start: date, end: date, competition_id: str | None) -> list[dict[str, Any]]:
        if end < start:
            raise ValueError("end date must be on or after start date")
        params: dict[str, Any] = {"dateFrom": start.isoformat(), "dateTo": end.isoformat()}
        if competition_id:
            params["competitions"] = competition_id
        payload = await self._get("matches", params)
        raw = payload.get("matches")
        if not isinstance(raw, list):
            raise ProviderError("Missing matches array in provider response.")
        records: list[dict[str, Any]] = []
        try:
            for item in raw:
                match = MatchRecord.model_validate(item)
                kickoff = match.utcDate
                if kickoff.tzinfo is None:
                    raise ProviderError("Provider kickoff timestamp has no timezone.")
                records.append({
                    "provider": self.name, "provider_fixture_id": str(match.id),
                    "competition_provider_id": str(match.competition.get("id", "")),
                    "competition_name": match.competition.get("name"),
                    "season": str(match.season.get("id", "")) or None,
                    "home_team_provider_id": str(match.homeTeam.get("id", "")),
                    "home_team_name": match.homeTeam.get("name"),
                    "away_team_provider_id": str(match.awayTeam.get("id", "")),
                    "away_team_name": match.awayTeam.get("name"),
                    "kickoff_at": kickoff.astimezone(timezone.utc),
                    "status": match.status.lower(),
                    "matchday": match.matchday,
                    "venue": match.venue,
                    "score": match.score,
                })
        except (ValidationError, TypeError, AttributeError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError("Invalid match record in provider response.") from exc
        return records

    async def fixtures(self, start: date, end: date, competition_id: str | None = None) -> list[dict[str, Any]]:
        return [m for m in await self._matches(start, end, competition_id)
                if m["status"] not in {"finished", "awarded"}]

    async def results(self, start: date, end: date, competition_id: str | None = None) -> list[dict[str, Any]]:
        return [m for m in await self._matches(start, end, competition_id)
                if m["status"] in {"finished", "awarded"}]

    async def standings(self, competition_id: str) -> list[dict[str, Any]]:
        competition_id = self._validate_path_id(competition_id, "competition id")
        payload = await self._get(f"competitions/{competition_id}/standings")
        raw = payload.get("standings")
        if not isinstance(raw, list):
            raise ProviderError("Missing standings array in provider response.")
        return raw

    async def match_statistics(self, fixture_id: str) -> Unsupported:
        return Unsupported("match_statistics", "football-data.org adapter does not expose this capability.")

    async def head_to_head(self, home_team_id: str, away_team_id: str) -> Unsupported:
        return Unsupported("head_to_head", "No verified H2H endpoint is implemented in this adapter.")

    async def odds(self, fixture_id: str) -> Unsupported:
        return Unsupported("odds", "Odds are not available from this adapter.")

    async def injuries(self, fixture_id: str) -> Unsupported:
        return Unsupported("injuries", "Injury data is not available from this adapter.")

    async def team_news(self, team_id: str) -> Unsupported:
        return Unsupported("team_news", "News data is not available from this adapter.")
