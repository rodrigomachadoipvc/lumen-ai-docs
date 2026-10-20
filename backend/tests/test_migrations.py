from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from lumen.db.models import Base


async def test_migrations_match_the_models(database_url: str) -> None:
    """Fails when a model changes without a matching Alembic migration."""

    def diff(connection: Connection) -> list[object]:
        context = MigrationContext.configure(connection)
        return list(compare_metadata(context, Base.metadata))

    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        differences = await connection.run_sync(diff)
    await engine.dispose()

    assert differences == []
