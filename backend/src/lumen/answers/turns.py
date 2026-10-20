"""Run one chat turn in the background and persist it, independently of the HTTP connection."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumen.answers.service import AnswerEvent, DoneEvent
from lumen.config import Settings
from lumen.db.models import Chat, Message, MessageRole
from lumen.observability import LLMTracer
from lumen.providers.chat import ChatMessage
from lumen.providers.errors import ProviderError

log = structlog.get_logger(__name__)

AnswerMode = Literal["answer", "agent"]
DEFAULT_TITLE = "New chat"


@dataclass(frozen=True)
class ErrorEvent:
    message: str


@dataclass(frozen=True)
class SavedEvent:
    """Last event: the ids of the stored user and assistant messages."""

    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID


TurnEvent = AnswerEvent | ErrorEvent | SavedEvent
Answerer = Callable[
    [str, Sequence[ChatMessage], Sequence[uuid.UUID] | None], AsyncIterator[AnswerEvent]
]


class TurnRunner:
    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        tracer: LLMTracer | None = None,
    ) -> None:
        self._sessions = sessions
        self._settings = settings
        self._tracer = tracer or LLMTracer()
        self._tasks: set[asyncio.Task[None]] = set()

    async def history(self, chat_id: uuid.UUID) -> list[ChatMessage]:
        """The last messages of the chat, as plain text (no sources or tool calls)."""
        limit = self._settings.history_messages
        if limit == 0:
            return []
        async with self._sessions() as session:
            rows = await session.scalars(
                select(Message)
                .where(Message.chat_id == chat_id, Message.error.is_(None))
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            recent = list(rows)
        return [
            ChatMessage("user" if m.role is MessageRole.USER else "assistant", m.content)
            for m in reversed(recent)
        ]

    def start(
        self,
        chat_id: uuid.UUID,
        content: str,
        answerer: Answerer,
        document_ids: Sequence[uuid.UUID] | None,
        mode: AnswerMode = "answer",
    ) -> asyncio.Queue[TurnEvent | None]:
        queue: asyncio.Queue[TurnEvent | None] = asyncio.Queue()
        task = asyncio.create_task(self._run(chat_id, content, answerer, document_ids, mode, queue))
        # Keep a reference so the task is not garbage-collected if the client disconnects.
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return queue

    async def wait(self) -> None:
        """Wait for every running turn (used by tests and on shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _run(
        self,
        chat_id: uuid.UUID,
        content: str,
        answerer: Answerer,
        document_ids: Sequence[uuid.UUID] | None,
        mode: AnswerMode,
        queue: asyncio.Queue[TurnEvent | None],
    ) -> None:
        try:
            history = await self.history(chat_id)
            user_message = Message(
                id=uuid.uuid7(), chat_id=chat_id, role=MessageRole.USER, content=content
            )
            async with self._sessions() as session:
                session.add(user_message)
                chat = await session.get(Chat, chat_id)
                if chat is not None and chat.title == DEFAULT_TITLE:
                    chat.title = content.strip().splitlines()[0][:80] or DEFAULT_TITLE
                await session.commit()

            assistant = Message(
                id=uuid.uuid7(), chat_id=chat_id, role=MessageRole.ASSISTANT, content=""
            )
            with self._tracer.trace(
                "chat-turn", session_id=str(chat_id), tags=[mode], input=content
            ) as root:
                try:
                    async for event in answerer(content, history, document_ids):
                        await queue.put(event)
                        if isinstance(event, DoneEvent):
                            assistant.content = event.answer
                            assistant.sources = event.sources
                            assistant.citations = event.citations
                            assistant.steps = event.steps
                            assistant.grounded = event.grounded
                            assistant.model = event.model
                except ProviderError as exc:
                    assistant.error = str(exc)
                    await queue.put(ErrorEvent(str(exc)))
                except Exception:
                    log.exception("chat_turn_failed", chat_id=str(chat_id))
                    assistant.error = "Something went wrong while answering."
                    await queue.put(ErrorEvent(assistant.error))
                root.update(
                    output=assistant.content or assistant.error,
                    metadata={
                        "grounded": assistant.grounded,
                        "citations": len(assistant.citations or []),
                        "model": assistant.model,
                    },
                    level="ERROR" if assistant.error else None,
                )

            async with self._sessions() as session:
                session.add(assistant)
                # Bump the chat to the top of the chat list.
                await session.execute(
                    update(Chat).where(Chat.id == chat_id).values(updated_at=func.now())
                )
                await session.commit()
            await queue.put(SavedEvent(user_message.id, assistant.id))
        except Exception:
            log.exception("chat_turn_not_saved", chat_id=str(chat_id))
            await queue.put(ErrorEvent("The message could not be saved."))
        finally:
            await queue.put(None)
