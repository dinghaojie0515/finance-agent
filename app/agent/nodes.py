import asyncio
import json
from datetime import datetime
from pathlib import Path

import yaml
from langchain_core.messages import AIMessage
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_openai import ChatOpenAI

from app.agent.state import AgentState
from app.conf.app_config import app_config
from app.core.log import logger
from app.models.mysql.column_info_mysql import ColumnInfoMySQL
from app.repositories.es.value_es_repository import ValueEsRepository
from app.repositories.mysql.finance_mysql_repository import FinanceMysqlRepository
from app.repositories.mysql.meta_mysql_repository import MetaMysqlRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository

PROMPTS_DIR = Path(__file__).parents[2] / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=app_config.llm.model_name,
        api_key=app_config.llm.api_key,
        base_url=app_config.llm.base_url,
    )


def _parse_json(text: str) -> list | dict:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        start_list = text.find("[")
        end_list = text.rfind("]")
        start_dict = text.find("{")
        end_dict = text.rfind("}")
        if start_list != -1 and (end_list > start_dict or start_dict == -1):
            return json.loads(text[start_list : end_list + 1])
        if start_dict != -1:
            return json.loads(text[start_dict : end_dict + 1])
        return []


def _column_from_mysql(column: ColumnInfoMySQL) -> dict:
    return {
        "id": column.id,
        "name": column.name,
        "type": column.type or "",
        "role": column.role or "",
        "examples": list(column.examples or []),
        "description": column.description or "",
        "alias": list(column.alias or []),
        "table_id": column.table_id or "",
    }


def _column_to_table_entry(column: dict) -> dict:
    return {
        "name": column.get("name"),
        "type": column.get("type"),
        "role": column.get("role"),
        "description": column.get("description"),
        "alias": column.get("alias", []),
        "examples": (column.get("examples") or [])[:10],
    }


def _metric_to_entry(metric: dict) -> dict:
    return {
        "name": metric.get("name"),
        "description": metric.get("description"),
        "relevant_columns": metric.get("relevant_columns", []),
        "alias": metric.get("alias", []),
    }


# ─────────────────── node functions ───────────────────

async def extract_keywords(state: AgentState) -> dict:
    logger.info("[extract_keywords] 开始提取关键词")
    llm = _get_llm()

    col_prompt = _load_prompt("extend_keywords_for_column_recall.prompt").format(query=state.query)
    metric_prompt = _load_prompt("extend_keywords_for_metric_recall.prompt").format(query=state.query)
    value_prompt = _load_prompt("extend_keywords_for_value_recall.prompt").format(query=state.query)

    col_resp, metric_resp, value_resp = await asyncio.gather(
        llm.ainvoke(col_prompt),
        llm.ainvoke(metric_prompt),
        llm.ainvoke(value_prompt),
    )

    column_keywords = _parse_json(col_resp.content)
    metric_keywords = _parse_json(metric_resp.content)
    value_keywords = _parse_json(value_resp.content)

    if not isinstance(column_keywords, list):
        column_keywords = []
    if not isinstance(metric_keywords, list):
        metric_keywords = []
    if not isinstance(value_keywords, list):
        value_keywords = []

    logger.info(f"[extract_keywords] 字段关键词: {column_keywords}")
    logger.info(f"[extract_keywords] 指标关键词: {metric_keywords}")
    logger.info(f"[extract_keywords] 取值关键词: {value_keywords}")

    return {
        "column_keywords": column_keywords,
        "metric_keywords": metric_keywords,
        "value_keywords": value_keywords,
    }


async def recall_column(
    state: AgentState,
    column_qdrant_repository: ColumnQdrantRepository,
    embedding_client: HuggingFaceEndpointEmbeddings,
) -> dict:
    logger.info("[recall_column] 开始向量召回字段信息")
    keywords = list(dict.fromkeys(state.column_keywords))[:10]
    if not keywords:
        return {"retrieved_columns": []}

    embeddings = await embedding_client.aembed_documents(keywords)
    seen_ids: set[str] = set()
    results = []
    for emb in embeddings:
        hits = await column_qdrant_repository.search(emb, score_threshold=0.6, limit=5)
        for hit in hits:
            col_id = hit.get("id", "")
            if col_id and col_id not in seen_ids:
                seen_ids.add(col_id)
                results.append(hit)

    logger.info(f"[recall_column] 召回字段数: {len(results)}")
    return {"retrieved_columns": results}


async def recall_metric(
    state: AgentState,
    metric_qdrant_repository: MetricQdrantRepository,
    embedding_client: HuggingFaceEndpointEmbeddings,
) -> dict:
    logger.info("[recall_metric] 开始向量召回指标信息")
    keywords = list(dict.fromkeys(state.metric_keywords))[:10]
    if not keywords:
        return {"retrieved_metrics": []}

    embeddings = await embedding_client.aembed_documents(keywords)
    seen_ids: set[str] = set()
    results = []
    for emb in embeddings:
        hits = await metric_qdrant_repository.search(emb, score_threshold=0.6, limit=5)
        for hit in hits:
            metric_id = hit.get("id", "")
            if metric_id and metric_id not in seen_ids:
                seen_ids.add(metric_id)
                results.append(hit)

    logger.info(f"[recall_metric] 召回指标数: {len(results)}")
    return {"retrieved_metrics": results}


async def recall_value(
    state: AgentState,
    value_es_repository: ValueEsRepository,
) -> dict:
    logger.info("[recall_value] 开始全文召回字段取值")
    keywords = list(dict.fromkeys(state.value_keywords))[:10]
    if not keywords:
        return {"retrieved_values": []}

    seen_ids: set[str] = set()
    results = []
    for kw in keywords:
        hits = await value_es_repository.search(kw, threshold=0.5, limit=3)
        for hit in hits:
            val_id = hit.get("id", "")
            if val_id and val_id not in seen_ids:
                seen_ids.add(val_id)
                results.append(hit)

    logger.info(f"[recall_value] 召回取值数: {len(results)}")
    return {"retrieved_values": results}


async def merge_retrieved_info(state: AgentState, meta_mysql_repository: MetaMysqlRepository) -> dict:
    """合并三路召回结果，补充指标关联字段、取值示例和主外键字段"""
    logger.info("[merge_retrieved_info] 合并召回信息")

    retrieved_columns_map: dict[str, dict] = {
        col["id"]: dict(col) for col in state.retrieved_columns if col.get("id")
    }

    for retrieved_metric in state.retrieved_metrics:
        for relevant_column in retrieved_metric.get("relevant_columns", []):
            if relevant_column not in retrieved_columns_map:
                column_info = await meta_mysql_repository.get_column_info_by_id(relevant_column)
                if column_info:
                    retrieved_columns_map[relevant_column] = _column_from_mysql(column_info)

    for retrieved_value in state.retrieved_values:
        column_value = retrieved_value.get("value")
        column_id = retrieved_value.get("column_id")
        if not column_id:
            continue
        if column_id not in retrieved_columns_map:
            column_info = await meta_mysql_repository.get_column_info_by_id(column_id)
            if column_info:
                retrieved_columns_map[column_id] = _column_from_mysql(column_info)
        if column_value and column_value not in retrieved_columns_map[column_id].get("examples", []):
            retrieved_columns_map[column_id].setdefault("examples", []).append(column_value)

    table_to_columns: dict[str, list[dict]] = {}
    for column in retrieved_columns_map.values():
        table_id = column.get("table_id", "")
        if not table_id:
            continue
        table_to_columns.setdefault(table_id, []).append(column)

    for table_id in list(table_to_columns.keys()):
        key_columns = await meta_mysql_repository.get_key_columns_by_table_id(table_id)
        existing_ids = {col.get("id") for col in table_to_columns[table_id]}
        for key_column in key_columns:
            if key_column.id not in existing_ids:
                table_to_columns[table_id].append(_column_from_mysql(key_column))

    table_infos: list[dict] = []
    for table_id, columns in table_to_columns.items():
        table_info = await meta_mysql_repository.get_table_info_by_id(table_id)
        table_infos.append(
            {
                "name": table_id,
                "role": table_info.role if table_info else "",
                "description": table_info.description if table_info else "",
                "columns": [_column_to_table_entry(col) for col in columns],
            }
        )

    metric_infos = [_metric_to_entry(m) for m in state.retrieved_metrics]
    logger.info(f"[merge_retrieved_info] 合并后表数: {len(table_infos)}, 指标数: {len(metric_infos)}")
    return {"table_infos": table_infos, "metric_infos": metric_infos}


async def filter_table(state: AgentState) -> dict:
    logger.info("[filter_table] 开始筛选相关表和字段")
    table_infos = [dict(t, columns=[dict(c) for c in t.get("columns", [])]) for t in state.table_infos]
    if not table_infos:
        return {"table_infos": [], "filtered_table_info": {}}

    table_infos_yaml = yaml.dump(table_infos, allow_unicode=True, default_flow_style=False)
    llm = _get_llm()
    prompt = _load_prompt("filter_table_info.prompt").format(
        query=state.query,
        table_infos=table_infos_yaml,
    )
    resp = await llm.ainvoke(prompt)
    filtered = _parse_json(resp.content)
    if not isinstance(filtered, dict):
        filtered = {}

    for table_info in table_infos[:]:
        table_name = table_info["name"]
        if table_name not in filtered:
            table_infos.remove(table_info)
            continue
        selected_columns = filtered[table_name]
        if not isinstance(selected_columns, list):
            selected_columns = []
        for column in table_info["columns"][:]:
            if column["name"] not in selected_columns:
                table_info["columns"].remove(column)

    filtered_table_info = {t["name"]: [c["name"] for c in t["columns"]] for t in table_infos}
    logger.info(f"[filter_table] 筛选后表数: {len(table_infos)}")
    return {"table_infos": table_infos, "filtered_table_info": filtered_table_info}


async def filter_metric(state: AgentState) -> dict:
    logger.info("[filter_metric] 开始筛选相关指标")
    metric_infos = [dict(m) for m in state.metric_infos]
    if not metric_infos:
        return {"metric_infos": [], "filtered_metric_names": []}

    metric_yaml = yaml.dump(metric_infos, allow_unicode=True, default_flow_style=False)
    llm = _get_llm()
    prompt = _load_prompt("filter_metric_info.prompt").format(
        query=state.query,
        metric_infos=metric_yaml,
    )
    resp = await llm.ainvoke(prompt)
    filtered = _parse_json(resp.content)
    if not isinstance(filtered, list):
        filtered = []

    for metric_info in metric_infos[:]:
        if metric_info.get("name") not in filtered:
            metric_infos.remove(metric_info)

    filtered_metric_names = [m.get("name") for m in metric_infos if m.get("name")]
    logger.info(f"[filter_metric] 筛选后指标数: {len(metric_infos)}")
    return {"metric_infos": metric_infos, "filtered_metric_names": filtered_metric_names}


async def add_extra_context(state: AgentState, meta_mysql_repository: MetaMysqlRepository) -> dict:
    """补充主外键字段，确保 JOIN 条件完整"""
    logger.info("[add_extra_context] 补充主外键字段")
    table_infos = [dict(t, columns=[dict(c) for c in t.get("columns", [])]) for t in state.table_infos]

    for table_info in table_infos:
        table_id = table_info["name"]
        existing_names = {c["name"] for c in table_info["columns"]}
        key_cols = await meta_mysql_repository.get_key_columns_by_table_id(table_id)
        for kc in key_cols:
            if kc.name not in existing_names:
                table_info["columns"].append(_column_to_table_entry(_column_from_mysql(kc)))
                existing_names.add(kc.name)

    extra_table_info = {t["name"]: [c["name"] for c in t["columns"]] for t in table_infos}
    return {"table_infos": table_infos, "extra_table_info": extra_table_info}


async def build_final_context(state: AgentState) -> dict:
    """构建最终传入 prompt 的表字段和指标信息字符串"""
    logger.info("[build_final_context] 构建最终上下文")

    table_list = []
    for table_info in state.table_infos:
        table_list.append(
            {
                "name": table_info.get("name"),
                "description": table_info.get("description", ""),
                "columns": table_info.get("columns", []),
            }
        )

    return {
        "final_table_info": yaml.dump(table_list, allow_unicode=True, default_flow_style=False),
        "final_metric_info": yaml.dump(state.metric_infos, allow_unicode=True, default_flow_style=False),
    }


async def generate_sql(state: AgentState) -> dict:
    logger.info("[generate_sql] 开始生成 SQL")

    now = datetime.now()
    date_info = f"当前日期：{now.strftime('%Y-%m-%d')}，当前时间：{now.strftime('%H:%M:%S')}"
    db_info = f"数据库类型：MySQL 8.0，数据库名：{app_config.db_finance.database}"

    llm = _get_llm()
    prompt = _load_prompt("generate_sql.prompt").format(
        date_info=date_info,
        db_info=db_info,
        query=state.query,
        table_infos=state.final_table_info,
        metric_infos=state.final_metric_info,
    )
    resp = await llm.ainvoke(prompt)
    sql = resp.content.strip()
    if sql.startswith("```"):
        sql = "\n".join(sql.split("\n")[1:])
    if sql.endswith("```"):
        sql = "\n".join(sql.split("\n")[:-1])
    sql = sql.strip()

    logger.info(f"[generate_sql] 生成 SQL: {sql}")
    return {"sql": sql, "sql_error": "", "messages": [AIMessage(content=f"正在生成 SQL...\n```sql\n{sql}\n```")]}


async def validate_sql(state: AgentState, finance_mysql_repository: FinanceMysqlRepository) -> dict:
    logger.info("[validate_sql] 开始验证 SQL")
    try:
        await finance_mysql_repository.validate_sql(state.sql)
        logger.info("[validate_sql] SQL 验证通过")
        return {"sql_error": ""}
    except Exception as e:
        err = str(e)
        logger.warning(f"[validate_sql] SQL 验证失败: {err}")
        return {"sql_error": err}


async def correct_sql(state: AgentState) -> dict:
    logger.info(f"[correct_sql] 第 {state.sql_correct_count + 1} 次修正 SQL")
    llm = _get_llm()
    prompt = _load_prompt("correct_sql.prompt").format(
        query=state.query,
        table_infos=state.final_table_info,
        sql=state.sql,
        error=state.sql_error,
    )
    resp = await llm.ainvoke(prompt)
    sql = resp.content.strip()
    if sql.startswith("```"):
        sql = "\n".join(sql.split("\n")[1:])
    if sql.endswith("```"):
        sql = "\n".join(sql.split("\n")[:-1])
    sql = sql.strip()

    logger.info(f"[correct_sql] 修正后 SQL: {sql}")
    return {
        "sql": sql,
        "sql_correct_count": state.sql_correct_count + 1,
        "messages": [AIMessage(content=f"SQL 修正中（第{state.sql_correct_count + 1}次）...\n```sql\n{sql}\n```")],
    }


async def execute_sql(state: AgentState, finance_mysql_repository: FinanceMysqlRepository) -> dict:
    logger.info("[execute_sql] 开始执行 SQL")
    try:
        result = await finance_mysql_repository.execute_sql(state.sql)
        logger.info(f"[execute_sql] 执行成功，返回行数: {len(result)}")
        result_json = json.dumps(result, ensure_ascii=False, default=str)
        return {
            "sql_result": result,
            "messages": [AIMessage(content=f"查询完成，共返回 {len(result)} 条数据：\n```json\n{result_json}\n```")],
        }
    except Exception as e:
        logger.error(f"[execute_sql] 执行失败: {e}")
        return {
            "sql_result": [],
            "messages": [AIMessage(content=f"SQL 执行失败：{e}")],
        }


# ─────────────────── routing ───────────────────

def should_correct_sql(state: AgentState) -> str:
    if state.sql_error and state.sql_correct_count < state.SQL_CORRECT_MAX:
        return "correct_sql"
    return "execute_sql"
