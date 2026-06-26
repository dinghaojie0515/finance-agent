from typing import Annotated

from langgraph.graph import add_messages
from pydantic import BaseModel, Field


class AgentState(BaseModel):
    query: str = Field(default="", description="用户查询问题")
    column_keywords: list[str] = Field(default_factory=list, description="字段召回关键词")
    metric_keywords: list[str] = Field(default_factory=list, description="指标召回关键词")
    value_keywords: list[str] = Field(default_factory=list, description="取值召回关键词")
    retrieved_columns: list[dict] = Field(default_factory=list, description="召回的字段信息列表")
    retrieved_metrics: list[dict] = Field(default_factory=list, description="召回的指标信息列表")
    retrieved_values: list[dict] = Field(default_factory=list, description="召回的字段值信息列表")
    table_infos: list[dict] = Field(default_factory=list, description="合并召回后的表信息列表")
    metric_infos: list[dict] = Field(default_factory=list, description="合并召回后的指标信息列表")
    filtered_table_info: dict[str, list[str]] = Field(default_factory=dict, description="筛选后的表字段映射")
    filtered_metric_names: list[str] = Field(default_factory=list, description="筛选后的指标名称列表")
    extra_table_info: dict[str, list[str]] = Field(default_factory=dict, description="补充主外键后的表字段映射")
    final_table_info: str = Field(default="", description="最终格式化后的表字段信息（YAML字符串）")
    final_metric_info: str = Field(default="", description="最终格式化后的指标信息（YAML字符串）")
    sql: str = Field(default="", description="生成的 SQL 语句")
    sql_error: str = Field(default="", description="SQL 验证错误信息")
    sql_correct_count: int = Field(default=0, description="SQL 修正次数")
    sql_result: list[dict] = Field(default_factory=list, description="SQL 执行结果")
    messages: Annotated[list, add_messages] = Field(default_factory=list, description="消息历史（流式输出用）")

    SQL_CORRECT_MAX: int = Field(default=3, description="最大SQL修正次数")
