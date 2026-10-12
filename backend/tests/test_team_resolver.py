from app.sports.team_resolver import TeamResolver, normalize_team_name

def test_normalizes_unicode_and_common_suffixes():
    assert normalize_team_name("  Atlético Madrid FC ") == "atletico madrid"

def test_exact_alias_is_preferred():
    resolver = TeamResolver([("1", "Arsenal"), ("2", "Arsenal Tula")], {"Gunners": "1"})
    assert resolver.resolve("Gunners").team_id == "1"

def test_ambiguous_low_confidence_names_are_not_forced():
    resolver = TeamResolver([("1", "United"), ("2", "United FC")], threshold=60, ambiguity_gap=10)
    result = resolver.resolve("United")
    assert result.status == "ambiguous"
    assert result.team_id is None

def test_unknown_name_is_unmatched():
    resolver = TeamResolver([("1", "Arsenal")])
    assert resolver.resolve("unknown club").status == "unmatched"
