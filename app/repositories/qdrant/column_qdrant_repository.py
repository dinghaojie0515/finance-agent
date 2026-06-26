import asyncio
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client import models

from app.conf.app_config import app_config
from app.core.log import logger
from app.models.qdrant.column_info_qdrant import ColumnInfoQdrant

COLLECTION_NAME = "finance_column_info"
UPSERT_MAX_RETRIES = 3


class ColumnQdrantRepository:
    def __init__(self, client: AsyncQdrantClient):
        self.client = client
        self.collection_name = COLLECTION_NAME

    async def ensure_collection(self) -> None:
        if not await self.client.collection_exists(self.collection_name):
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=app_config.qdrant.embedding_size,
                    distance=models.Distance.COSINE,
                ),
            )

    async def recreate_collection(self) -> None:
        if await self.client.collection_exists(self.collection_name):
            await self.client.delete_collection(self.collection_name)
        await self.ensure_collection()

    async def upsert_embedding(
        self,
        ids: list[uuid.UUID],
        embeddings: list[list[float]],
        payloads: list[ColumnInfoQdrant],
    ) -> None:
        points = [
            models.PointStruct(id=str(i), vector=e, payload=p)
            for i, e, p in zip(ids, embeddings, payloads)
        ]
        for attempt in range(1, UPSERT_MAX_RETRIES + 1):
            try:
                await self.client.upsert(collection_name=self.collection_name, points=points)
                return
            except Exception as e:
                if attempt >= UPSERT_MAX_RETRIES:
                    raise
                wait_s = attempt * 2
                logger.warning(
                    f"[qdrant-col] upsert 失败，{wait_s}s 后重试 ({attempt}/{UPSERT_MAX_RETRIES}): {e}"
                )
                await asyncio.sleep(wait_s)

    async def search(
        self,
        embedding: list[float],
        score_threshold: float = 0.6,
        limit: int = 5,
    ) -> list[ColumnInfoQdrant]:
        results = await self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            score_threshold=score_threshold,
            limit=limit,
        )
        return [point.payload for point in results.points]
