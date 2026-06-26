from functools import partial

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    add_extra_context,
    build_final_context,
    correct_sql,
    execute_sql,
    extract_keywords,
    filter_metric,
    filter_table,
    generate_sql,
    merge_retrieved_info,
    recall_column,
    recall_metric,
    recall_value,
    should_correct_sql,
    validate_sql,
)
from app.agent.state import AgentState
from app.repositories.es.value_es_repository import ValueEsRepository
from app.repositories.mysql.finance_mysql_repository import FinanceMysqlRepository
from app.repositories.mysql.meta_mysql_repository import MetaMysqlRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


def build_graph(
    meta_mysql_repository: MetaMysqlRepository,
    finance_mysql_repository: FinanceMysqlRepository,
    column_qdrant_repository: ColumnQdrantRepository,
    metric_qdrant_repository: MetricQdrantRepository,
    value_es_repository: ValueEsRepository,
    embedding_client: HuggingFaceEndpointEmbeddings,
):
    builder = StateGraph(AgentState)

    builder.add_node("extract_keywords", extract_keywords)
    builder.add_node(
        "recall_column",
        partial(recall_column, column_qdrant_repository=column_qdrant_repository, embedding_client=embedding_client),
    )
    builder.add_node(
        "recall_metric",
        partial(recall_metric, metric_qdrant_repository=metric_qdrant_repository, embedding_client=embedding_client),
    )
    builder.add_node(
        "recall_value",
        partial(recall_value, value_es_repository=value_es_repository),
    )
    builder.add_node(
        "merge_retrieved_info",
        partial(merge_retrieved_info, meta_mysql_repository=meta_mysql_repository),
    )
    builder.add_node("filter_table", filter_table)
    builder.add_node("filter_metric", filter_metric)
    builder.add_node(
        "add_extra_context",
        partial(add_extra_context, meta_mysql_repository=meta_mysql_repository),
    )
    builder.add_node("build_final_context", build_final_context)
    builder.add_node("generate_sql", generate_sql)
    builder.add_node(
        "validate_sql",
        partial(validate_sql, finance_mysql_repository=finance_mysql_repository),
    )
    builder.add_node("correct_sql", correct_sql)
    builder.add_node(
        "execute_sql",
        partial(execute_sql, finance_mysql_repository=finance_mysql_repository),
    )

    builder.add_edge(START, "extract_keywords")

    builder.add_edge("extract_keywords", "recall_column")
    builder.add_edge("extract_keywords", "recall_metric")
    builder.add_edge("extract_keywords", "recall_value")

    builder.add_edge("recall_column", "merge_retrieved_info")
    builder.add_edge("recall_metric", "merge_retrieved_info")
    builder.add_edge("recall_value", "merge_retrieved_info")

    builder.add_edge("merge_retrieved_info", "filter_table")
    builder.add_edge("merge_retrieved_info", "filter_metric")

    builder.add_edge("filter_table", "add_extra_context")
    builder.add_edge("filter_metric", "add_extra_context")

    builder.add_edge("add_extra_context", "build_final_context")
    builder.add_edge("build_final_context", "generate_sql")
    builder.add_edge("generate_sql", "validate_sql")
    builder.add_conditional_edges(
        "validate_sql",
        should_correct_sql,
        {"correct_sql": "correct_sql", "execute_sql": "execute_sql"},
    )
    builder.add_edge("correct_sql", "validate_sql")
    builder.add_edge("execute_sql", END)

    return builder.compile()
