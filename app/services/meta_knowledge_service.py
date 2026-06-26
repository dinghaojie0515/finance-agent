import uuid
from pathlib import Path

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from omegaconf import OmegaConf

from app.conf.meta_config import MetaConfig
from app.core.log import logger
from app.models.es.value_info_es import ValueInfoES
from app.models.mysql.column_info_mysql import ColumnInfoMySQL
from app.models.mysql.column_metric_mysql import ColumnMetricMySQL
from app.models.mysql.metric_info_mysql import MetricInfoMySQL
from app.models.mysql.table_info_mysql import TableInfoMySQL
from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant
from app.models.qdrant.metric_info_qdrant import MetricInfoQdrant
from app.repositories.es.value_es_repository import ValueEsRepository
from app.repositories.mysql.finance_mysql_repository import FinanceMysqlRepository
from app.repositories.mysql.meta_mysql_repository import MetaMysqlRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


class MetaKnowledgeService:
    def __init__(
        self,
        meta_mysql_repository: MetaMysqlRepository,
        finance_mysql_repository: FinanceMysqlRepository,
        column_qdrant_repository: ColumnQdrantRepository,
        embedding_client: HuggingFaceEndpointEmbeddings,
        value_es_repository: ValueEsRepository,
        metric_qdrant_repository: MetricQdrantRepository,
    ):
        self.meta_mysql_repository = meta_mysql_repository
        self.finance_mysql_repository = finance_mysql_repository
        self.column_qdrant_repository = column_qdrant_repository
        self.embedding_client = embedding_client
        self.value_es_repository = value_es_repository
        self.metric_qdrant_repository = metric_qdrant_repository

    async def build(self, config_file: Path) -> None:
        context = OmegaConf.load(config_file)
        schema = OmegaConf.structured(MetaConfig)
        meta_config: MetaConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))
        logger.info("加载配置文件完成")

        column_infos: list[ColumnInfoMySQL] = []
        if meta_config.tables:
            column_infos = await self._save_table_info_to_meta_db(meta_config)
            logger.info("保存表信息到 financemeta 数据库完成")
            await self._save_column_info_to_qdrant(column_infos)
            logger.info("为字段信息建立向量索引完成")
            await self._save_value_info_to_es(column_infos, meta_config)
            logger.info("为字段取值建立全文索引完成")

        if meta_config.metrics:
            valid_column_ids = {c.id for c in column_infos}
            if not valid_column_ids:
                for table in meta_config.tables or []:
                    for column in table.columns:
                        valid_column_ids.add(f"{table.name}.{column.name}")
            metric_infos = await self._save_metric_info_to_meta_db(meta_config, valid_column_ids)
            logger.info("保存指标信息到 financemeta 数据库完成")
            await self._save_metric_info_to_qdrant(metric_infos)
            logger.info("为指标信息建立向量索引完成")

    async def _save_table_info_to_meta_db(self, meta_config: MetaConfig) -> list[ColumnInfoMySQL]:
        table_infos: list[TableInfoMySQL] = []
        column_infos: list[ColumnInfoMySQL] = []

        for table in meta_config.tables:
            column_types = await self.finance_mysql_repository.get_column_types(table.name)
            table_info = TableInfoMySQL(
                id=table.name,
                name=table.name,
                role=table.role,
                description=table.description,
            )
            table_infos.append(table_info)

            for column in table.columns:
                if column.name not in column_types:
                    logger.warning(f"[build] 跳过不存在的字段: {table.name}.{column.name}")
                    continue
                column_values = await self.finance_mysql_repository.get_column_values(table.name, column.name)
                column_info = ColumnInfoMySQL(
                    id=f"{table.name}.{column.name}",
                    name=column.name,
                    type=column_types.get(column.name, "varchar"),
                    role=column.role,
                    examples=column_values,
                    description=column.description,
                    alias=column.alias,
                    table_id=table.name,
                )
                column_infos.append(column_info)

        # async with self.meta_mysql_repository.session.begin():
        #     await self.meta_mysql_repository.save_table_infos(table_infos)
        #     await self.meta_mysql_repository.save_column_infos(column_infos)

        return column_infos

    def _to_qdrant(self, column: ColumnInfoMySQL) -> ColumnInfoQdrant:
        return ColumnInfoQdrant(
            id=column.id,
            name=column.name,
            type=column.type or "",
            role=column.role or "",
            examples=column.examples or [],
            description=column.description or "",
            alias=column.alias or [],
            table_id=column.table_id or "",
        )

    async def _save_column_info_to_qdrant(self, column_infos: list[ColumnInfoMySQL]) -> None:
        await self.column_qdrant_repository.recreate_collection()

        points: list[dict] = []
        for col in column_infos:
            payload = self._to_qdrant(col)
            points.append({"id": uuid.uuid4(), "text": col.name, "payload": payload})
            points.append({"id": uuid.uuid4(), "text": col.description, "payload": payload})
            for alia in col.alias:
                points.append({"id": uuid.uuid4(), "text": alia, "payload": payload})

        total = len(points)
        batch_size = 20
        logger.info(f"[qdrant-col] 开始写入字段向量，共 {total} 条")
        for i in range(0, total, batch_size):
            batch_points = points[i : i + batch_size]
            batch_texts = [p["text"] for p in batch_points]
            batch_embeddings = await self.embedding_client.aembed_documents(batch_texts)
            await self.column_qdrant_repository.upsert_embedding(
                [p["id"] for p in batch_points],
                batch_embeddings,
                [p["payload"] for p in batch_points],
            )
            logger.info(f"[qdrant-col] 已完成 {min(i + batch_size, total)}/{total}")

    async def _save_value_info_to_es(self, column_infos: list[ColumnInfoMySQL], meta_config: MetaConfig) -> None:
        await self.value_es_repository.ensure_index()

        sync_map: dict[str, bool] = {}
        for table in meta_config.tables:
            for col in table.columns:
                sync_map[f"{table.name}.{col.name}"] = col.sync

        value_infos: list[ValueInfoES] = []
        sync_column_count = 0
        for col in column_infos:
            if sync_map.get(col.id, False):
                sync_column_count += 1
                values = await self.finance_mysql_repository.get_column_values(col.table_id or "", col.name, 5000)
                for v in values:
                    value_infos.append(
                        ValueInfoES(
                            id=f"{col.id}.{v}",
                            value=v,
                            type=col.type or "",
                            column_id=col.id,
                            column_name=col.name,
                            table_id=col.table_id or "",
                            table_name=col.table_id or "",
                        )
                    )

        logger.info(
            f"[es-value] sync 字段 {sync_column_count} 个，待写入取值 {len(value_infos)} 条"
        )
        await self.value_es_repository.upsert_values(value_infos)
        logger.info(f"[es-value] 全文索引写入完成，共 {len(value_infos)} 条")

    async def _save_metric_info_to_meta_db(
        self, meta_config: MetaConfig, valid_column_ids: set[str]
    ) -> list[MetricInfoMySQL]:
        metric_infos: list[MetricInfoMySQL] = []
        column_metric_infos: list[ColumnMetricMySQL] = []

        for metric in meta_config.metrics:
            valid_relevant_columns = []
            for rc in metric.relevant_columns:
                if rc not in valid_column_ids:
                    logger.warning(f"[build] 跳过不存在的指标关联字段: {rc}")
                    continue
                valid_relevant_columns.append(rc)

            metric_info = MetricInfoMySQL(
                id=metric.name,
                name=metric.name,
                description=metric.description,
                relevant_columns=valid_relevant_columns,
                alias=metric.alias,
            )
            metric_infos.append(metric_info)
            for rc in valid_relevant_columns:
                column_metric_infos.append(ColumnMetricMySQL(column_id=rc, metric_id=metric.name))

        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.save_metric_infos(metric_infos)
            await self.meta_mysql_repository.save_column_metric_infos(column_metric_infos)

        return metric_infos

    def _metric_to_qdrant(self, m: MetricInfoMySQL) -> MetricInfoQdrant:
        return MetricInfoQdrant(
            id=m.id,
            name=m.name or "",
            description=m.description or "",
            relevant_columns=m.relevant_columns or [],
            alias=m.alias or [],
        )

    async def _save_metric_info_to_qdrant(self, metric_infos: list[MetricInfoMySQL]) -> None:
        await self.metric_qdrant_repository.recreate_collection()

        points: list[dict] = []
        for m in metric_infos:
            payload = self._metric_to_qdrant(m)
            points.append({"id": uuid.uuid4(), "text": m.name or "", "payload": payload})
            points.append({"id": uuid.uuid4(), "text": m.description or m.name or "", "payload": payload})
            for alias in (m.alias or []):
                points.append({"id": uuid.uuid4(), "text": alias, "payload": payload})

        total = len(points)
        batch_size = 10
        logger.info(f"[qdrant-metric] 开始写入指标向量，共 {total} 条")
        for i in range(0, total, batch_size):
            batch_points = points[i : i + batch_size]
            batch_texts = [p["text"] for p in batch_points]
            batch_embeddings = await self.embedding_client.aembed_documents(batch_texts)
            await self.metric_qdrant_repository.upsert_embeddings(
                [p["id"] for p in batch_points],
                batch_embeddings,
                [p["payload"] for p in batch_points],
            )
            logger.info(f"[qdrant-metric] 已完成 {min(i + batch_size, total)}/{total}")
