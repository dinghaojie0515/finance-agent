from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import finance_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.es.value_es_repository import ValueEsRepository
from app.repositories.mysql.finance_mysql_repository import FinanceMysqlRepository
from app.repositories.mysql.meta_mysql_repository import MetaMysqlRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


async def get_meta_session() -> AsyncGenerator[AsyncSession, None]:
    async with meta_mysql_client_manager.session_factory() as session:
        yield session


async def get_finance_session() -> AsyncGenerator[AsyncSession, None]:
    async with finance_mysql_client_manager.session_factory() as session:
        yield session


def get_meta_mysql_repository(session: AsyncSession = None) -> MetaMysqlRepository:
    return MetaMysqlRepository(session)


def get_finance_mysql_repository(session: AsyncSession = None) -> FinanceMysqlRepository:
    return FinanceMysqlRepository(session)


def get_column_qdrant_repository() -> ColumnQdrantRepository:
    return ColumnQdrantRepository(qdrant_client_manager.client)


def get_metric_qdrant_repository() -> MetricQdrantRepository:
    return MetricQdrantRepository(qdrant_client_manager.client)


def get_value_es_repository() -> ValueEsRepository:
    return ValueEsRepository(es_client_manager.client)


def get_embedding_client():
    return embedding_client_manager.client
