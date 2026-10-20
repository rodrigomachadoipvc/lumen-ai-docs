"""Chats: create, list, read, rename, delete, and ask questions with streamed answers (SSE)."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from lumen.answers.service import DeltaEvent, DoneEvent, ResetEvent, SourcesEvent, StepEvent
from lumen.answers.turns import DEFAULT_TITLE, AnswerMode, ErrorEvent, SavedEvent, TurnEvent
from lumen.api.deps import ContainerDep, SessionDep
from lumen.api.errors import not_found
from lumen.db.models import Chat, MessageRole

router = APIRouter(prefix="/chats", tags=["chats"])


class ChatCreate(BaseModel):
    title: str = Field(default=DEFAULT_TITLE, min_length=1, max_length=200)


class ChatUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    sources: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    grounded: bool | None
    model: str | None
    error: str | None
    created_at: datetime


class ChatDetail(ChatOut):
    messages: list[MessageOut]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    mode: AnswerMode = "answer"
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


async def get_chat(chat_id: uuid.UUID, session: SessionDep) -> Chat:
    chat = await session.get(Chat, chat_id)
    if chat is None:
        raise not_found("Chat")
    return chat


ChatDep = Annotated[Chat, Depends(get_chat)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_chat(body: ChatCreate, session: SessionDep) -> ChatOut:
    chat = Chat(id=uuid.uuid7(), title=body.title.strip())
    session.add(chat)
    await session.commit()
    await session.refresh(chat)
    return ChatOut.model_validate(chat)


@router.get("")
async def list_chats(session: SessionDep) -> list[ChatOut]:
    chats = await session.scalars(select(Chat).order_by(Chat.updated_at.desc()))
    return [ChatOut.model_validate(c) for c in chats]


@router.get("/{chat_id}")
async def get_chat_detail(chat_id: uuid.UUID, session: SessionDep) -> ChatDetail:
    chat = await session.scalar(
        select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.messages))
    )
    if chat is None:
        raise not_found("Chat")
    return ChatDetail.model_validate(chat)


@router.patch("/{chat_id}")
async def rename_chat(body: ChatUpdate, chat: ChatDep, session: SessionDep) -> ChatOut:
    chat.title = body.title.strip()
    await session.commit()
    await session.refresh(chat)
    return ChatOut.model_validate(chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat: ChatDep, session: SessionDep) -> Response:
    await session.delete(chat)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def to_sse(event: TurnEvent) -> ServerSentEvent:
    match event:
        case SourcesEvent(sources):
            return ServerSentEvent(event="sources", data={"sources": sources})
        case DeltaEvent(text):
            return ServerSentEvent(event="delta", data={"text": text})
        case StepEvent(step):
            return ServerSentEvent(event="step", data=step)
        case DoneEvent():
            return ServerSentEvent(
                event="done",
                data={
                    "answer": event.answer,
                    "citations": event.citations,
                    "grounded": event.grounded,
                    "model": event.model,
                },
            )
        case ErrorEvent(message):
            return ServerSentEvent(event="error", data={"message": message})
        case ResetEvent():
            return ServerSentEvent(event="reset", data={})
        case SavedEvent(user_id, assistant_id):
            return ServerSentEvent(
                event="saved",
                data={"user_message_id": str(user_id), "assistant_message_id": str(assistant_id)},
            )


@router.post("/{chat_id}/messages", response_class=EventSourceResponse)
async def send_message(
    body: MessageCreate, chat: ChatDep, container: ContainerDep
) -> AsyncIterator[ServerSentEvent]:
    """Ask a question. Streams `sources`, `delta`… (agent mode adds `step` and `reset`), then
    `done` and
    `saved`; `error` replaces `done` if the model fails. The answer is saved even if the client
    disconnects."""
    answerer = container.agent.run if body.mode == "agent" else container.answers.answer_turn
    queue = container.turns.start(chat.id, body.content.strip(), answerer, body.document_ids)
    while (event := await queue.get()) is not None:
        yield to_sse(event)
