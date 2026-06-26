from typing import Union

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.conf.app_config import DBConfig, app_config


class MysqlClientManager:
    def __init__(self, db_config: DBConfig):
        self.db_config = db_config
        self.engine: Union[AsyncEngine, None] = None
        self.session_factory = None

    def _get_url(self) -> str:
        c = self.db_config
        return (
            f"mysql+asyncmy://{c.user}:{c.password}@{c.host}:{c.port}/{c.database}"
            "?charset=utf8mb4"
        )

    def init(self) -> None:
        self.engine = create_async_engine(
            self._get_url(),
            pool_size=10,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    async def close(self) -> None:
        if self.engine:
            await self.engine.dispose()


meta_mysql_client_manager = MysqlClientManager(app_config.db_meta)
finance_mysql_client_manager = MysqlClientManager(app_config.db_finance)
