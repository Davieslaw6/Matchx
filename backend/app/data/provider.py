"""Data-provider adapters (football-data.org, API-Football): shared HTTP core + normalisation."""
from __future__ import annotations
import re
import time
from datetime import datetime, timezone
import httpx
from pydantic import BaseModel


class ProviderError(Exception):
    pass


class ProviderRestricted(ProviderError):
    """The plan/key does not cover the requested competition/season."""


class RetryableProviderError(ProviderError):
    pass


class NormMatch(BaseModel):
    provider_fixture_id: int
    competition_code: str
    season: int
    matchday: int | None
    utc_kickoff: datetime
    status: str                     # normalised: TIMED | FINISHED | POSTPONED | CANCELLED | IN_PLAY | other
    home_id: int
    home_name: str
    home_short: str | None = None
    home_tla: str | None = None
    away_id: int
    away_name: str
    away_short: str | None = None
    away_tla: str | None = None
    home_goals: int | None = None   # None = unavailable (never 0-filled)
    away_goals: int | None = None


class BaseHttpProvider:
    name = "base"

    def __init__(self, base_url: str, headers: dict, timeout_s: float = 10.0, max_retries: int = 2,
                 cache_ttl_s: int = 300, min_interval_s: float = 6.5,
                 transport: httpx.BaseTransport | None = None, sleep=time.sleep, clock=time.monotonic):
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, headers=headers, transport=transport)
        self.max_retries, self.cache_ttl_s, self.min_interval_s = max_retries, cache_ttl_s, min_interval_s
        self._sleep, self._clock = sleep, clock
        self._cache: dict[tuple, tuple[float, dict]] = {}
        self._last_call: float | None = None

    def _inspect(self, data: dict) -> None:
        """Hook: raise ProviderRestricted / RetryableProviderError / ProviderError for error bodies."""

    def _get(self, path: str, params: dict | None = None) -> dict:
        key = (path, tuple(sorted((params or {}).items())))
        hit = self._cache.get(key)
        if hit and self._clock() - hit[0] < self.cache_ttl_s:
            return hit[1]
        last_err: Exception | None = None
        for _ in range(self.max_retries + 1):
            if self._last_call is not None:
                wait = self.min_interval_s - (self._clock() - self._last_call)
                if wait > 0:
                    self._sleep(wait)
            self._last_call = self._clock()
            try:
                r = self._client.get(path, params=params)
            except httpx.TransportError as e:
                last_err = e
                continue
            if r.status_code == 403:
                raise ProviderRestricted(f"{path}: not available on this plan")
            if r.status_code == 429 or r.status_code >= 500:
                last_err = ProviderError(f"{path}: HTTP {r.status_code}")
                if r.status_code == 429:
                    self._sleep(min(float(r.headers.get("Retry-After", 1)), 30))
                continue
            if r.status_code != 200:
                raise ProviderError(f"{path}: HTTP {r.status_code}")
            data = r.json()
            try:
                self._inspect(data)
            except RetryableProviderError as e:
                last_err = e
                continue
            self._cache[key] = (self._clock(), data)
            return data
        raise ProviderError(f"Provider unavailable after {self.max_retries + 1} attempts: {last_err}")

    def get_matches(self, competition_code: str, season: int | None = None) -> list[NormMatch]:
        raise NotImplementedError


# ---------------- football-data.org ----------------
_FD_STATUS = {"SCHEDULED": "TIMED", "TIMED": "TIMED", "FINISHED": "FINISHED", "POSTPONED": "POSTPONED",
              "CANCELLED": "CANCELLED", "IN_PLAY": "IN_PLAY", "PAUSED": "IN_PLAY"}


def normalise_match(raw: dict, competition_code: str) -> NormMatch:
    ft = (raw.get("score") or {}).get("fullTime") or {}
    start = (raw.get("season") or {}).get("startDate")
    kick = datetime.fromisoformat(raw["utcDate"].replace("Z", "+00:00")).astimezone(timezone.utc)
    season = int(start[:4]) if start else (kick.year if kick.month >= 8 else kick.year - 1)
    h, a = raw["homeTeam"], raw["awayTeam"]
    return NormMatch(
        provider_fixture_id=raw["id"], competition_code=competition_code, season=season,
        matchday=raw.get("matchday"), utc_kickoff=kick, status=_FD_STATUS.get(raw["status"], raw["status"]),
        home_id=h["id"], home_name=h["name"], home_short=h.get("shortName"), home_tla=h.get("tla"),
        away_id=a["id"], away_name=a["name"], away_short=a.get("shortName"), away_tla=a.get("tla"),
        home_goals=ft.get("home"), away_goals=ft.get("away"),
    )


class FootballDataOrgClient(BaseHttpProvider):
    name = "football-data.org"

    def __init__(self, api_key: str, base_url: str, **kw):
        if not api_key:
            raise ProviderError("FOOTBALL_DATA_API_KEY is not configured")
        super().__init__(base_url, {"X-Auth-Token": api_key}, **kw)

    def get_matches(self, competition_code: str, season: int | None = None) -> list[NormMatch]:
        data = self._get(f"/competitions/{competition_code}/matches", {"season": season} if season else None)
        out = []
        for raw in data.get("matches", []):
            try:
                out.append(normalise_match(raw, competition_code))
            except (KeyError, ValueError, TypeError):
                continue  # malformed record: skip rather than guess
        return out


# ---------------- API-Football (api-sports.io v3) ----------------
AF_LEAGUE_IDS = {"PL": 39, "PD": 140, "SA": 135, "BL1": 78, "FL1": 61}
_AF_STATUS = {**dict.fromkeys(["NS", "TBD"], "TIMED"), **dict.fromkeys(["FT", "AET", "PEN"], "FINISHED"),
              "PST": "POSTPONED", **dict.fromkeys(["CANC", "ABD", "AWD", "WO"], "CANCELLED"),
              **dict.fromkeys(["1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"], "IN_PLAY")}


def normalise_af_fixture(raw: dict, competition_code: str) -> NormMatch:
    fx, lg, t = raw["fixture"], raw["league"], raw["teams"]
    kick = datetime.fromisoformat(fx["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
    status = _AF_STATUS.get(fx["status"]["short"], fx["status"]["short"])
    hg = ag = None
    if status == "FINISHED":   # 90-minute score preferred; fall back to goals
        ft = (raw.get("score") or {}).get("fulltime") or {}
        g = raw.get("goals") or {}
        hg = ft.get("home") if ft.get("home") is not None else g.get("home")
        ag = ft.get("away") if ft.get("away") is not None else g.get("away")
    m = re.search(r"(\d+)\s*$", lg.get("round") or "")
    return NormMatch(
        provider_fixture_id=fx["id"], competition_code=competition_code, season=int(lg["season"]),
        matchday=int(m.group(1)) if m else None, utc_kickoff=kick, status=status,
        home_id=t["home"]["id"], home_name=t["home"]["name"], away_id=t["away"]["id"], away_name=t["away"]["name"],
        home_goals=hg, away_goals=ag)


class ApiFootballClient(BaseHttpProvider):
    name = "api-football"

    def __init__(self, api_key: str, base_url: str, **kw):
        if not api_key:
            raise ProviderError("API_FOOTBALL_API_KEY is not configured")
        kw.setdefault("min_interval_s", 6.5)
        super().__init__(base_url, {"x-apisports-key": api_key}, **kw)

    def _inspect(self, data: dict) -> None:
        errs = data.get("errors")
        if not errs:
            return
        if isinstance(errs, list):
            errs = {str(i): e for i, e in enumerate(errs)}
        text = "; ".join(f"{k}: {v}" for k, v in errs.items())
        if "rateLimit" in errs:
            raise RetryableProviderError(text)          # per-minute limit: back off and retry
        if "plan" in errs:
            raise ProviderRestricted(text)               # plan does not cover this season/league
        raise ProviderError(text)                        # bad token, daily quota ("requests"), bad params

    def get_matches(self, competition_code: str, season: int | None = None) -> list[NormMatch]:
        league = AF_LEAGUE_IDS.get(competition_code)
        if league is None:
            raise ProviderError(f"No API-Football league id configured for {competition_code}")
        if season is None:
            now = datetime.now(timezone.utc)
            season = now.year if now.month >= 8 else now.year - 1
        data = self._get("/fixtures", {"league": league, "season": season})
        out = []
        for raw in data.get("response", []):
            try:
                out.append(normalise_af_fixture(raw, competition_code))
            except (KeyError, ValueError, TypeError):
                continue
        return out
