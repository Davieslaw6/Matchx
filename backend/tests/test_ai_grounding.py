import pytest

from app.ai.grounding import verify_numeric_grounding
from app.ai.tools import ToolRegistry

def test_grounding_accepts_values_supported_by_retrieved_data():
    assert verify_numeric_grounding(
        "The stored result is 2–1 on 2025-01-01; the model estimate is 45%.",
        [{"home_goals": 2, "away_goals": 1, "match_date": "2025-01-01", "home_win": 0.45}],
    )

def test_grounding_rejects_unsupported_number():
    assert not verify_numeric_grounding("The team has won 7 matches.", [{"wins": 4}])

def test_grounding_allows_non_numeric_unavailable_data_statement():
    assert verify_numeric_grounding("No stored odds are available for this fixture.", [])


@pytest.mark.asyncio
async def test_tool_registry_rejects_unknown_tools_and_extra_arguments():
    registry = ToolRegistry()
    assert (await registry.dispatch("execute_python", "{}", None))["status"] == "unsupported_tool"
    invalid = await registry.dispatch("search_fixtures", '{"query":"Arsenal","sql":"DROP TABLE teams"}', None)
    assert invalid["status"] == "invalid_arguments"
