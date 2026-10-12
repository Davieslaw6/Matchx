"""Conservative team matching: aliases/exact normalized names before fuzzy suggestions."""
import unicodedata
from dataclasses import dataclass
from rapidfuzz import fuzz, process

@dataclass(frozen=True)
class TeamCandidate:
    team_id: str
    name: str
    score: float

@dataclass(frozen=True)
class TeamResolution:
    status: str
    team_id: str | None
    normalized_query: str
    candidates: tuple[TeamCandidate, ...] = ()

_SUFFIXES = {"fc", "cf", "afc", "sc", "club", "football", "soccer"}

def normalize_team_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    tokens = "".join(char if char.isalnum() else " " for char in text).split()
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)

class TeamResolver:
    def __init__(self, teams: list[tuple[str, str]], aliases: dict[str, str] | None = None,
                 threshold: float = 92.0, ambiguity_gap: float = 4.0):
        if not 0 <= threshold <= 100:
            raise ValueError("threshold must be in [0, 100]")
        self.teams = {team_id: name for team_id, name in teams}
        self.aliases = {normalize_team_name(alias): team_id for alias, team_id in (aliases or {}).items()
                        if team_id in self.teams}
        self.names: dict[str, list[str]] = {}
        for team_id, name in teams:
            self.names.setdefault(normalize_team_name(name), []).append(team_id)
        self.threshold = threshold
        self.ambiguity_gap = ambiguity_gap

    def resolve(self, query: str, limit: int = 5) -> TeamResolution:
        normalized = normalize_team_name(query)
        if not normalized:
            return TeamResolution("unmatched", None, normalized)
        if normalized in self.aliases:
            team_id = self.aliases[normalized]
            return TeamResolution("matched", team_id, normalized,
                                  (TeamCandidate(team_id, self.teams[team_id], 100.0),))
        exact = self.names.get(normalized, [])
        if len(exact) == 1:
            team_id = exact[0]
            return TeamResolution("matched", team_id, normalized,
                                  (TeamCandidate(team_id, self.teams[team_id], 100.0),))
        choices = list(self.names.keys())
        ranked = process.extract(normalized, choices, scorer=fuzz.WRatio, limit=max(1, limit))
        candidates: list[TeamCandidate] = []
        for name, score, _ in ranked:
            for team_id in self.names[name]:
                candidates.append(TeamCandidate(team_id, self.teams[team_id], float(score)))
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        if not candidates or candidates[0].score < self.threshold:
            return TeamResolution("unmatched", None, normalized, tuple(candidates))
        if len(candidates) > 1 and candidates[0].score - candidates[1].score < self.ambiguity_gap:
            return TeamResolution("ambiguous", None, normalized, tuple(candidates))
        return TeamResolution("matched", candidates[0].team_id, normalized, tuple(candidates))
