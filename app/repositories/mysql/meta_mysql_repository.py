from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mysql.column_info_mysql import ColumnInfoMySQL
from app.models.mysql.column_metric_mysql import ColumnMetricMySQL
from app.models.mysql.metric_info_mysql import MetricInfoMySQL
from app.models.mysql.table_info_mysql import TableInfoMySQL


class MetaMysqlRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_table_infos(self, table_infos: list[TableInfoMySQL]) -> None:
        for t in table_infos:
            await self.session.merge(t)

    async def save_column_infos(self, column_infos: list[ColumnInfoMySQL]) -> None:
        for c in column_infos:
            await self.session.merge(c)

    async def save_metric_infos(self, metric_infos: list[MetricInfoMySQL]) -> None:
        for m in metric_infos:
            await self.session.merge(m)

    async def save_column_metric_infos(self, column_metric_infos: list[ColumnMetricMySQL]) -> None:
        for cm in column_metric_infos:
            await self.session.merge(cm)

    async def get_column_info_by_id(self, column_id: str) -> ColumnInfoMySQL | None:
        return await self.session.get(ColumnInfoMySQL, column_id)

    async def get_table_info_by_id(self, table_id: str) -> TableInfoMySQL | None:
        return await self.session.get(TableInfoMySQL, table_id)

    async def get_key_columns_by_table_id(self, table_id: str) -> list[ColumnInfoMySQL]:
        sql = """
            SELECT * FROM column_info
            WHERE table_id = :table_id
            AND role IN ('primary_key', 'foreign_key')
        """
        query = select(ColumnInfoMySQL).from_statement(text(sql))
        result = await self.session.execute(query, {"table_id": table_id})
        return list(result.scalars().fetchall())
