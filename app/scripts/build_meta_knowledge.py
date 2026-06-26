import asyncio
from argparse import ArgumentParser
from pathlib import Path

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import finance_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.es.value_es_repository import ValueEsRepository
from app.repositories.mysql.finance_mysql_repository import FinanceMysqlRepository
from app.repositories.mysql.meta_mysql_repository import MetaMysqlRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.meta_knowledge_service import MetaKnowledgeService


async def build(config_path: Path) -> None:
    meta_mysql_client_manager.init()
    finance_mysql_client_manager.init()
    qdrant_client_manager.init()
    embedding_client_manager.init()
    es_client_manager.init()

    async with (
        meta_mysql_client_manager.session_factory() as meta_session,
        finance_mysql_client_manager.session_factory() as finance_session,
    ):
        meta_repo = MetaMysqlRepository(meta_session)
        finance_repo = FinanceMysqlRepository(finance_session)
        column_qdrant_repo = ColumnQdrantRepository(qdrant_client_manager.client)
        metric_qdrant_repo = MetricQdrantRepository(qdrant_client_manager.client)
        value_es_repo = ValueEsRepository(es_client_manager.client)
        embedding_client = embedding_client_manager.client

        service = MetaKnowledgeService(
            meta_mysql_repository=meta_repo,
            finance_mysql_repository=finance_repo,
            column_qdrant_repository=column_qdrant_repo,
            embedding_client=embedding_client,
            value_es_repository=value_es_repo,
            metric_qdrant_repository=metric_qdrant_repo,
        )
        await service.build(config_path)

    await meta_mysql_client_manager.close()
    await finance_mysql_client_manager.close()
    await qdrant_client_manager.close()
    await es_client_manager.close()


if __name__ == "__main__":
    parser = ArgumentParser(description="构建金融问数元数据知识库")
    parser.add_argument("-c", "--conf", required=True, help="meta_config.yaml 路径")
    args = parser.parse_args()
    asyncio.run(build(Path(args.conf)))
