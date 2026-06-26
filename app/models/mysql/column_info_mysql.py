from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.mysql.base import Base


class ColumnInfoMySQL(Base):
    __tablename__ = "column_info"

    id: Mapped[str] = mapped_column(String(128), primary_key=True, comment="列编号(table.column)")
    name: Mapped[str | None] = mapped_column(String(128), comment="列名称")
    type: Mapped[str | None] = mapped_column(String(64), comment="数据类型")
    role: Mapped[str | None] = mapped_column(String(32), comment="列角色(primary_key/foreign_key/measure/dimension)")
    examples: Mapped[list | None] = mapped_column(JSON, comment="数据示例")
    description: Mapped[str | None] = mapped_column(Text, comment="列描述")
    alias: Mapped[list | None] = mapped_column(JSON, comment="列别名")
    table_id: Mapped[str | None] = mapped_column(String(64), comment="所属表编号")
