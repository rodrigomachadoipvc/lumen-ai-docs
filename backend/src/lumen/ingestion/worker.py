"""In-process background queue for ingestion.

One document at a time: embedding runs on the local GPU/CPU, so parallelism would not help.
A restart loses nothing, because pending documents are re-queued from the database on startup.
"""

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable

import structlog

log = structlog.get_logger(__name__)


class IngestionWorker:
    def __init__(self, handler: Callable[[uuid.UUID], Awaitable[None]]) -> None:
        self._handler = handler
        self._queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="ingestion-worker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def enqueue(self, document_id: uuid.UUID) -> None:
        self._queue.put_nowait(document_id)

    async def join(self) -> None:
        """Wait until every queued document has been processed (used by tests and the seed)."""
        await self._queue.join()

    async def _run(self) -> None:
        while True:
            document_id = await self._queue.get()
            try:
                await self._handler(document_id)
            except Exception:
                # The handler records failures itself; this only protects the loop.
                log.exception("ingestion_worker_error", document_id=str(document_id))
            finally:
                self._queue.task_done()
