import httpx
import pytest
import respx

from app.sports.football_data_org import FootballDataOrgProvider, ProviderError

@pytest.mark.asyncio
async def test_competitions_are_normalized_from_provider_payload():
    with respx.mock(base_url="https://api.football-data.org/v4") as mock:
        route = mock.get("/competitions").mock(return_value=httpx.Response(200, json={
            "competitions": [{"id": 2021, "code": "PL", "name": "Premier League",
                              "area": {"name": "England"}}]
        }))
        async with httpx.AsyncClient() as client:
            provider = FootballDataOrgProvider("test-token", client=client, max_retries=0)
            records = await provider.competitions()
        assert route.called
        assert records[0]["provider_id"] == "2021"
        assert records[0]["code"] == "PL"
        assert records[0]["name"] == "Premier League"

@pytest.mark.asyncio
async def test_missing_required_payload_shape_fails_closed():
    with respx.mock(base_url="https://api.football-data.org/v4") as mock:
        mock.get("/competitions").mock(return_value=httpx.Response(200, json={"unexpected": []}))
        async with httpx.AsyncClient() as client:
            provider = FootballDataOrgProvider("test-token", client=client, max_retries=0)
            with pytest.raises(ProviderError, match="Missing competitions"):
                await provider.competitions()

def test_unsupported_markets_are_explicit_not_empty_success():
    provider = FootballDataOrgProvider("test-token")
    assert isinstance(provider.capabilities.supports_odds, bool)
    assert provider.capabilities.supports_odds is False

@pytest.mark.asyncio
async def test_raw_payload_sink_receives_source_json_before_normalized_return():
    stored = []
    async def sink(payload):
        stored.append(payload)
    with respx.mock(base_url="https://api.football-data.org/v4") as mock:
        mock.get("/competitions").mock(return_value=httpx.Response(200, json={
            "competitions": [{"id": 2021, "code": "PL", "name": "Premier League",
                              "area": {"name": "England"}}]
        }))
        async with httpx.AsyncClient() as client:
            provider = FootballDataOrgProvider("test-token", client=client,
                                               max_retries=0, raw_payload_sink=sink)
            normalized = await provider.competitions()
    assert normalized[0]["name"] == "Premier League"
    assert stored[0]["payload"]["competitions"][0]["id"] == 2021
    assert len(stored[0]["content_hash"]) == 64
