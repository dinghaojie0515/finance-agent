from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class FinanceMysqlRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_column_types(self, table_name: str) -> dict[str, str]:
        result = await self.session.execute(text(f"SHOW COLUMNS FROM `{table_name}`"))
        rows = result.mappings().fetchall()
        return {row["Field"]: row["Type"] for row in rows}

    async def get_column_values(self, table_name: str, column_name: str, limit: int = 20) -> list[str]:
        sql = f"SELECT DISTINCT `{column_name}` FROM `{table_name}` WHERE `{column_name}` IS NOT NULL LIMIT {limit}"
        result = await self.session.execute(text(sql))
        return [str(row[0]) for row in result.fetchall()]

    async def validate_sql(self, sql: str) -> None:
        await self.session.execute(text(f"EXPLAIN {sql}"))

    async def execute_sql(self, sql: str) -> list[dict]:
        result = await self.session.execute(text(sql))
        return [dict(row) for row in result.mappings().fetchall()]
