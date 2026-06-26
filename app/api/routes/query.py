import json
import uuid
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import build_graph
from app.api.dependencies import (
    get_column_qdrant_repository,
    get_embedding_client,
    get_finance_session,
    get_meta_session,
    get_metric_qdrant_repository,
    get_value_es_repository,
)
from app.core.context import request_id_ctx_var
from app.core.log import logger
from app.repositories.es.value_es_repository import ValueEsRepository
from app.repositories.mysql.finance_mysql_repository import FinanceMysqlRepository
from app.repositories.mysql.meta_mysql_repository import MetaMysqlRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository

router = APIRouter()

NODE_LABELS: dict[str, str] = {
    "extract_keywords": "提取关键词",
    "recall_column": "召回相关字段",
    "recall_metric": "召回相关指标",
    "recall_value": "召回字段取值",
    "merge_retrieved_info": "合并召回信息",
    "filter_table": "筛选表与字段",
    "filter_metric": "筛选相关指标",
    "add_extra_context": "补充关联字段",
    "build_final_context": "构建查询上下文",
    "generate_sql": "生成 SQL",
    "validate_sql": "验证 SQL",
    "correct_sql": "修正 SQL",
    "execute_sql": "执行查询",
}


class QueryRequest(BaseModel):
    query: str


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _summarize_step(node_name: str, output: dict[str, Any]) -> str:
    if node_name == "extract_keywords":
        return (
            f"字段 {len(output.get('column_keywords', []))} · "
            f"指标 {len(output.get('metric_keywords', []))} · "
            f"取值 {len(output.get('value_keywords', []))}"
        )
    if node_name == "recall_column":
        return f"召回 {len(output.get('retrieved_columns', []))} 个字段"
    if node_name == "recall_metric":
        return f"召回 {len(output.get('retrieved_metrics', []))} 个指标"
    if node_name == "recall_value":
        return f"召回 {len(output.get('retrieved_values', []))} 条取值"
    if node_name == "merge_retrieved_info":
        return (
            f"合并 {len(output.get('table_infos', []))} 张表 · "
            f"{len(output.get('metric_infos', []))} 个指标"
        )
    if node_name == "filter_table":
        tables = output.get("filtered_table_info") or {}
        return f"保留 {len(tables)} 张表"
    if node_name == "filter_metric":
        names = output.get("filtered_metric_names") or []
        return f"保留 {len(names)} 个指标"
    if node_name == "validate_sql":
        return "通过" if not output.get("sql_error") else "失败，准备修正"
    if node_name == "execute_sql":
        rows = output.get("sql_result") or []
        return f"返回 {len(rows)} 行"
    if node_name == "generate_sql" or node_name == "correct_sql":
        return "SQL 已生成"
    return "完成"


async def _event_stream(query: str, graph) -> AsyncGenerator[str, None]:
    yield _sse({"type": "start", "content": query})

    async for event in graph.astream({"query": query}, stream_mode="updates"):
        for node_name, node_output in event.items():
            yield _sse(
                {
                    "type": "step",
                    "node": node_name,
                    "label": NODE_LABELS.get(node_name, node_name),
                    "detail": _summarize_step(node_name, node_output),
                }
            )

            if node_name in {"generate_sql", "correct_sql"} and node_output.get("sql"):
                yield _sse(
                    {
                        "type": "sql",
                        "node": node_name,
                        "content": node_output["sql"],
                    }
                )

            if node_name == "execute_sql" and node_output.get("sql_result") is not None:
                yield _sse(
                    {
                        "type": "result",
                        "content": node_output["sql_result"],
                    }
                )

            msgs = node_output.get("messages", [])
            for msg in msgs:
                content = msg.content if hasattr(msg, "content") else str(msg)
                yield _sse({"type": "message", "node": node_name, "content": content})

    yield _sse({"type": "done", "content": "completed"})


@router.post("/query")
async def query(
    request: QueryRequest,
    meta_session: AsyncSession = Depends(get_meta_session),
    finance_session: AsyncSession = Depends(get_finance_session),
    column_qdrant_repo: ColumnQdrantRepository = Depends(get_column_qdrant_repository),
    metric_qdrant_repo: MetricQdrantRepository = Depends(get_metric_qdrant_repository),
    value_es_repo: ValueEsRepository = Depends(get_value_es_repository),
    embedding_client=Depends(get_embedding_client),
):
    request_id = str(uuid.uuid4())
    request_id_ctx_var.set(request_id)
    logger.info(f"收到查询请求: {request.query}")

    meta_repo = MetaMysqlRepository(meta_session)
    finance_repo = FinanceMysqlRepository(finance_session)

    graph = build_graph(
        meta_mysql_repository=meta_repo,
        finance_mysql_repository=finance_repo,
        column_qdrant_repository=column_qdrant_repo,
        metric_qdrant_repository=metric_qdrant_repo,
        value_es_repository=value_es_repo,
        embedding_client=embedding_client,
    )

    return StreamingResponse(
        _event_stream(request.query, graph),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )
