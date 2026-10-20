import asyncio
from collections.abc import Sequence
from typing import Any

import pytest
from httpx2 import AsyncClient

from lumen.agent.loop import FINAL_ANSWER_NUDGE, Agent
from lumen.agent.tools import DocumentTools, SourceRegistry, ToolError
from lumen.answers.service import (
    AnswerEvent,
    DeltaEvent,
    DoneEvent,
    ResetEvent,
    SourcesEvent,
    StepEvent,
)
from lumen.container import Container
from lumen.providers.chat import ChatCompletion, ToolCall
from lumen.seed import DEFAULT_SAMPLES, sample_files, seed
from tests.fakes import FakeChat, FakeEmbeddings
from tests.test_answers import parse_sse


def call(name: str, **arguments: Any) -> ChatCompletion:
    return ChatCompletion(
        text="",
        tool_calls=(ToolCall(id=f"call-{name}", name=name, arguments=arguments),),
        stop_reason="tool_calls",
    )


@pytest.fixture
async def corpus(container: Container) -> None:
    await seed(container, sample_files(DEFAULT_SAMPLES))


def make_agent(container: Container, chat: FakeChat, **limits: Any) -> Agent:
    return Agent(
        session_factory=container.sessions, embedder=container.embedder, chat=chat, **limits
    )


async def run(agent: Agent, question: str) -> list[AnswerEvent]:
    return [event async for event in agent.run(question, [], None)]


def tools_for(container: Container, registry: SourceRegistry | None = None) -> DocumentTools:
    return DocumentTools(
        session_factory=container.sessions,
        embedder=container.embedder,
        registry=registry or SourceRegistry(),
    )


# --- The loop ---------------------------------------------------------------------------


async def test_agent_searches_then_answers_with_citations(
    container: Container, corpus: None
) -> None:
    chat = FakeChat(call("search_documents", query="vacation days"), "You get 25 days [1].")

    events = await run(make_agent(container, chat), "How many vacation days?")

    steps = [e.step for e in events if isinstance(e, StepEvent)]
    assert [(s["tool"], s["error"]) for s in steps] == [("search_documents", None)]
    assert steps[0]["sources"][0] == 1
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer == "You get 25 days [1]." and done.grounded
    assert done.steps == steps
    # The second model call received the tool result as numbered sources.
    tool_message = chat.calls[1]["messages"][-1]
    assert tool_message.role == "tool" and '<source id="1"' in tool_message.content
    assert chat.calls[0]["tools"] and "Answer in English" in chat.calls[0]["messages"][0].content


async def test_text_streamed_before_a_tool_call_is_reset(
    container: Container, corpus: None
) -> None:
    thinking_aloud = ChatCompletion(
        text="Let me check.",
        tool_calls=(ToolCall("c1", "search_documents", {"query": "vacation"}),),
        stop_reason="tool_calls",
    )
    chat = FakeChat(thinking_aloud, "25 days [1].")

    events = await run(make_agent(container, chat), "Vacation?")

    kinds = [type(e) for e in events]
    assert kinds.index(DeltaEvent) < kinds.index(ResetEvent) < kinds.index(StepEvent)


async def test_tool_errors_are_returned_to_the_model(container: Container, corpus: None) -> None:
    chat = FakeChat(
        call("search_documents"),  # missing "query"
        call("get_document_section", document="nope.pdf", page=1),
        call("search_documents", query="vacation"),
        "25 days [1].",
    )

    events = await run(make_agent(container, chat), "Vacation?")

    steps = [e.step for e in events if isinstance(e, StepEvent)]
    assert "Invalid arguments for search_documents: query" in steps[0]["error"]
    assert "No document matches 'nope.pdf'" in steps[1]["error"]
    assert steps[2]["error"] is None
    assert chat.calls[1]["messages"][-1].content.startswith("Error: Invalid arguments")


async def test_step_limit_forces_a_final_answer_without_tools(
    container: Container, corpus: None
) -> None:
    chat = FakeChat(
        call("search_documents", query="a"),
        call("search_documents", query="b"),
        "Done [1].",
    )

    events = await run(make_agent(container, chat, max_steps=2), "Question?")

    assert chat.calls[2]["tools"] == []
    assert chat.calls[2]["messages"][-1].content == FINAL_ANSWER_NUDGE
    assert isinstance(events[-1], DoneEvent) and events[-1].answer == "Done [1]."


async def test_slow_tools_time_out(container: Container, corpus: None) -> None:
    class SlowEmbeddings(FakeEmbeddings):
        async def embed_query(self, text: str) -> list[float]:
            await asyncio.sleep(1)
            return await super().embed_query(text)

    chat = FakeChat(call("search_documents", query="x"), "I could not find it.")
    agent = Agent(
        session_factory=container.sessions,
        embedder=SlowEmbeddings(),
        chat=chat,
        tool_timeout_s=0.05,
    )

    events = await run(agent, "Question?")

    step = next(e.step for e in events if isinstance(e, StepEvent))
    assert "timed out" in step["error"]


async def test_answer_without_looking_anything_up_is_rejected(
    container: Container, corpus: None
) -> None:
    chat = FakeChat("Paris is the capital of France.")

    events = await run(make_agent(container, chat), "What is the capital of France?")

    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer == "I couldn't find information about that in the documents."
    assert done.grounded is False
    assert isinstance(events[-2], SourcesEvent) and events[-2].sources == []


# --- The tools --------------------------------------------------------------------------


async def test_documents_can_be_named_loosely(container: Container, corpus: None) -> None:
    tools = tools_for(container)

    result = await tools.call(
        "get_document_section", {"document": "Regulamento de Teletrabalho", "page": 3}
    )

    assert "regulamento-teletrabalho.pdf, page 3" in result.summary
    assert "Artigo 7.º" in result.content


async def test_section_by_heading(container: Container, corpus: None) -> None:
    result = await tools_for(container).call(
        "get_document_section", {"document": "employee-handbook.md", "heading": "birthday"}
    )

    assert result.source_numbers == (1,)
    assert "birthday off" in result.content


async def test_compare_and_list(container: Container, corpus: None) -> None:
    registry = SourceRegistry()
    tools = tools_for(container, registry)

    compared = await tools.call(
        "compare_documents",
        {
            "question": "equipment",
            "documents": ["employee handbook", "regulamento-teletrabalho.pdf"],
        },
    )
    listed = await tools.call("list_documents", {})

    assert compared.content.count("<document name=") == 2
    assert len(registry.hits) == len(compared.source_numbers) > 2
    assert "regulamento-teletrabalho.pdf" in listed.content and "5 pages" in listed.content


async def test_registry_numbers_are_stable(container: Container, corpus: None) -> None:
    registry = SourceRegistry()
    tools = tools_for(container, registry)

    first = await tools.call("search_documents", {"query": "vacation days"})
    again = await tools.call("search_documents", {"query": "vacation days"})

    assert first.source_numbers == again.source_numbers
    assert len(registry.hits) == len(first.source_numbers)


async def test_unknown_tool(container: Container) -> None:
    with pytest.raises(ToolError, match="Unknown tool"):
        await tools_for(container).call("delete_everything", {})


# --- API --------------------------------------------------------------------------------


async def test_agent_mode_over_the_api(client: AsyncClient, chat: FakeChat, corpus: None) -> None:
    chat.queue(call("search_documents", query="vacation days"), "You get 25 days [1].")
    chat_id = (await client.post("/chats", json={})).json()["id"]

    response = await client.post(
        f"/chats/{chat_id}/messages", json={"content": "Vacation?", "mode": "agent"}
    )

    events = parse_sse(response.text)
    names: Sequence[str] = [name for name, _ in events]
    assert "step" in names and names[-2:] == ["done", "saved"]
    saved = (await client.get(f"/chats/{chat_id}")).json()["messages"][1]
    assert saved["steps"][0]["tool"] == "search_documents"
    assert saved["citations"][0]["number"] == 1
