"""
Unit API tests: ensure route-defined ORM tables exist on the shared test engine.

Root ``tests/conftest.py`` calls ``Base.metadata.create_all`` before
``cortex.api.main`` is imported, so tables declared only in route modules
(``agent_definitions``, ``skills``, ``model_providers``, etc.) are omitted.
Re-run ``create_all`` after importing the app so those tables exist for
endpoint tests that use the real ``get_db`` session.
"""

import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True, loop_scope="session")
async def _ensure_api_route_tables(_engine):
    import cortex.api.main  # noqa: F401 — registers route models on Base.metadata

    from cortex.platform.database.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
