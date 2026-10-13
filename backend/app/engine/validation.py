import math
from .errors import InsufficientDataError


def validate_prediction(p: dict, tol: float = 1e-6) -> None:
    """Hard checks before a prediction may be shown or stored."""
    r = p["result"]
    if abs(sum(r.values()) - 1.0) > tol:
        raise InsufficientDataError("1X2 probabilities do not sum to 1")
    values = list(r.values()) + list(p["over"].values()) + list(p["under"].values()) + list(p["btts"].values())
    if any((not math.isfinite(v)) or v < -tol or v > 1 + tol for v in values):
        raise InsufficientDataError("Probability outside [0, 1]")
    for k in p["over"]:
        if abs(p["over"][k] + p["under"][k] - 1.0) > tol:
            raise InsufficientDataError(f"over/under {k} inconsistent")
    if p["truncated_probability_mass"] > 1e-3:
        raise InsufficientDataError("Scoreline range truncates too much probability")
