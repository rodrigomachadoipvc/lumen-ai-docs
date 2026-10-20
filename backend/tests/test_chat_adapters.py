import pytest
from pydantic import SecretStr

from lumen.config import Settings
from lumen.providers.anthropic_chat import to_anthropic_messages, to_anthropic_tools
from lumen.providers.chat import ChatMessage, ToolCall, ToolSpec, build_chat_provider
from lumen.providers.errors import ProviderError
from lumen.providers.ollama_chat import to_ollama_messages, to_ollama_tools
from lumen.providers.openai_chat import to_openai_messages

CALL_A = ToolCall(id="a", name="search_documents", arguments={"query": "férias"})
CALL_B = ToolCall(id="b", name="list_documents", arguments={})
HISTORY = [
    ChatMessage("user", "Quantos dias de férias?"),
    ChatMessage("assistant", "", tool_calls=(CALL_A, CALL_B)),
    ChatMessage("tool", "25 dias", tool_call_id="a", tool_name="search_documents"),
    ChatMessage("tool", "3 documentos", tool_call_id="b", tool_name="list_documents"),
    ChatMessage("assistant", "São 25 dias [1]."),
]
TOOL = ToolSpec("search_documents", "Search", {"type": "object", "properties": {}})


def test_anthropic_groups_tool_results_into_one_user_message() -> None:
    converted = to_anthropic_messages(HISTORY)

    assert [m["role"] for m in converted] == ["user", "assistant", "user", "assistant"]
    assert [b["type"] for b in converted[1]["content"]] == ["tool_use", "tool_use"]
    results = converted[2]["content"]
    assert [(r["tool_use_id"], r["content"]) for r in results] == [
        ("a", "25 dias"),
        ("b", "3 documentos"),
    ]
    assert to_anthropic_tools([TOOL])[0]["input_schema"] == TOOL.parameters


def test_anthropic_sends_original_blocks_back_unchanged() -> None:
    raw = [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": "Hi"}]

    converted = to_anthropic_messages([ChatMessage("assistant", "Hi", raw=raw)])

    assert converted == [{"role": "assistant", "content": raw}]


def test_openai_conversion() -> None:
    converted = to_openai_messages("rules", HISTORY)

    assert converted[0] == {"role": "system", "content": "rules"}
    assert converted[2]["tool_calls"][0]["function"] == {
        "name": "search_documents",
        "arguments": '{"query": "f\\u00e9rias"}',
    }
    assert converted[3] == {"role": "tool", "tool_call_id": "a", "content": "25 dias"}


def test_ollama_conversion() -> None:
    converted = to_ollama_messages("rules", HISTORY)

    assert converted[2]["tool_calls"][0] == {
        "function": {"name": "search_documents", "arguments": {"query": "férias"}}
    }
    assert converted[3] == {"role": "tool", "content": "25 dias", "tool_name": "search_documents"}
    assert to_ollama_tools([TOOL])[0]["function"]["name"] == "search_documents"


def test_hosted_providers_need_a_key() -> None:
    for provider in ("anthropic", "openai"):
        settings = Settings(_env_file=None, chat_provider=provider)
        with pytest.raises(ProviderError, match="API_KEY"):
            build_chat_provider(settings)


def test_default_models() -> None:
    settings = Settings(
        _env_file=None, chat_provider="anthropic", anthropic_api_key=SecretStr("test-key")
    )

    assert build_chat_provider(settings).model == "claude-opus-5-5"
    assert build_chat_provider(Settings(_env_file=None)).model == "qwen3.5:4b"
