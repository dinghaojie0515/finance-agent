from elasticsearch import AsyncElasticsearch

from app.conf.app_config import app_config
from app.core.log import logger
from app.models.es.value_info_es import ValueInfoES

INDEX_NAME = app_config.es.index_name


class ValueEsRepository:
    def __init__(self, client: AsyncElasticsearch):
        self.client = client
        self.es_index_name = INDEX_NAME

    async def ensure_index(self) -> None:
        if not await self.client.indices.exists(index=self.es_index_name):
            await self.client.indices.create(
                index=self.es_index_name,
                mappings={
                    "dynamic": False,
                    "properties": {
                        "id": {"type": "keyword"},
                        "value": {"type": "text", "analyzer": "standard"},
                        "type": {"type": "keyword"},
                        "column_id": {"type": "keyword"},
                        "column_name": {"type": "keyword"},
                        "table_id": {"type": "keyword"},
                        "table_name": {"type": "keyword"},
                    },
                },
            )

    async def upsert_values(self, value_infos: list[ValueInfoES], batch_size: int = 200) -> None:
        if not value_infos:
            logger.warning("[es-value] 无待写入取值，跳过 bulk")
            return
        for i in range(0, len(value_infos), batch_size):
            batch = value_infos[i : i + batch_size]
            operations = []
            for v in batch:
                operations.append({"index": {"_index": self.es_index_name, "_id": v["id"]}})
                operations.append(dict(v))
            result = await self.client.bulk(operations=operations)
            if result.get("errors"):
                failed = sum(1 for item in result["items"] if "error" in item.get("index", {}))
                raise RuntimeError(f"[es-value] bulk 写入失败 {failed}/{len(batch)} 条")

    async def search(
        self,
        keyword: str,
        threshold: float = 0.6,
        limit: int = 5,
    ) -> list[ValueInfoES]:
        result = await self.client.search(
            index=self.es_index_name,
            query={"match": {"value": keyword}},
            min_score=threshold,
            size=limit,
        )
        return [hit["_source"] for hit in result["hits"]["hits"]]
