import httpx
import pytest
import respx
from pydantic import SecretStr

from app.ai.provider import LLMProviderError, OpenAIResponsesProvider
from app.config import Settings

class FakeRegistry:
    def schemas(self):
        return [{"type": "function", "name": "search_fixtures", "parameters": {"type": "object"}}]
    async def dispatch(self, name, raw_arguments, db):
        assert name == "search_fixtures"
        assert raw_arguments == '{"query":"Arsenal"}'
        return {"status": "ok", "count": 2, "fixtures": []}

@pytest.mark.asyncio
async def test_provider_handles_function_call_and_returns_final_answer():
    settings = Settings(llm_api_key=SecretStr("test-token"), llm_model="test-model")
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/responses").mock(side_effect=[
            httpx.Response(200, json={
                "id": "resp_1",
                "output": [{"type": "function_call", "name": "search_fixtures",
                            "call_id": "call_1", "arguments": '{"query":"Arsenal"}'}],
            }),
            httpx.Response(200, json={
                "id": "resp_2",
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "The database returned 2 fixtures."}
                ]}],
            }),
        ])
        provider = OpenAIResponsesProvider(settings, registry=FakeRegistry())
        result = await provider.answer([{"role": "user", "content": "Find Arsenal fixtures."}], db=None)
    assert result.text == "The database returned 2 fixtures."
    assert result.tool_calls == [{"name": "search_fixtures", "status": "ok"}]
    assert mock.call_count == 2

def test_provider_requires_server_side_api_key():
    with pytest.raises(LLMProviderError, match="not configured"):
        OpenAIResponsesProvider(Settings(llm_api_key=None))
