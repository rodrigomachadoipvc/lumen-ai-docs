from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI

from lumen.answers.service import AnswerService
from lumen.config import Settings
from lumen.container import Container
from lumen.observability import LLMTracer, build_llm_tracer, setup_opentelemetry
from lumen.providers.chat import ChatCompletion
from lumen.seed import DEFAULT_SAMPLES, sample_files, seed
from tests.fakes import FakeChat


class RecordedObservation:
    def __init__(self, name: str, kwargs: dict[str, Any]) -> None:
        self.name = name
        self.kwargs = kwargs
        self.updates: dict[str, Any] = {}

    def update(self, **fields: Any) -> None:
        self.updates.update(fields)


class FakeLangfuse:
    def __init__(self) -> None:
        self.observations: list[RecordedObservation] = []
        self.flushed = False

    @contextmanager
    def start_as_current_observation(self, *, name: str, **kwargs: Any) -> Iterator[Any]:
        observation = RecordedObservation(name, kwargs)
        self.observations.append(observation)
        yield observation

    def flush(self) -> None:
        self.flushed = True


def test_disabled_tracer_is_a_no_op() -> None:
    tracer = build_llm_tracer(Settings(_env_file=None))

    with tracer.observe("x", as_type="generation", model="m") as observation:
        observation.update(output="ignored")
    tracer.flush()

    assert tracer.enabled is False


async def test_answer_records_retrieval_and_generation(container: Container) -> None:
    await seed(container, sample_files(DEFAULT_SAMPLES))
    langfuse = FakeLangfuse()
    chat = FakeChat(
        ChatCompletion(text="25 days [1].", usage={"input_tokens": 900, "output_tokens": 12})
    )
    container.settings.min_similarity = 0.1
    service = AnswerService(
        session_factory=container.sessions,
        embedder=container.embedder,
        chat=chat,
        settings=container.settings,
        tracer=LLMTracer(langfuse),
    )

    _ = [event async for event in service.answer("How many vacation days?")]

    retrieval, generation = langfuse.observations
    assert retrieval.name == "retrieval" and retrieval.kwargs["as_type"] == "retriever"
    assert retrieval.updates["output"][0]["filename"]
    assert generation.kwargs["as_type"] == "generation"
    assert generation.kwargs["model"] == "fake-chat"
    assert generation.kwargs["input"][0]["role"] == "system"
    assert generation.updates["usage_details"] == {"input": 900, "output": 12}
    assert generation.updates["output"] == "25 days [1]."


def test_opentelemetry_is_only_set_up_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app",
        lambda app, **kwargs: calls.append(kwargs["excluded_urls"]),
    )

    setup_opentelemetry(FastAPI(), Settings(_env_file=None))
    setup_opentelemetry(
        FastAPI(), Settings(_env_file=None, otel_exporter_endpoint="http://localhost:4318")
    )

    assert calls == ["health"]
