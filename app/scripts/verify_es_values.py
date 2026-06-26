"""Verify ES column-value index after build_meta_knowledge."""

import asyncio
from argparse import ArgumentParser
from pathlib import Path

from omegaconf import OmegaConf

from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import finance_mysql_client_manager
from app.conf.app_config import app_config
from app.conf.meta_config import MetaConfig
from app.repositories.es.value_es_repository import ValueEsRepository
from app.repositories.mysql.finance_mysql_repository import FinanceMysqlRepository


async def verify(config_path: Path) -> None:
    ctx = OmegaConf.load(config_path)
    schema = OmegaConf.structured(MetaConfig)
    meta: MetaConfig = OmegaConf.to_object(OmegaConf.merge(schema, ctx))

    sync_column_ids: list[str] = []
    for table in meta.tables or []:
        for column in table.columns:
            if column.sync:
                sync_column_ids.append(f"{table.name}.{column.name}")

    print(f"[config] sync=true columns: {len(sync_column_ids)}")

    es_client_manager.init()
    finance_mysql_client_manager.init()
    idx = app_config.es.index_name
    value_repo = ValueEsRepository(es_client_manager.client)

    try:
        exists = await es_client_manager.client.indices.exists(index=idx)
        print(f"[es] index '{idx}' exists: {exists}")
        if not exists:
            print("[es] FAIL: index missing — ES step likely wrote nothing")
            return

        doc_count = (await es_client_manager.client.count(index=idx))["count"]
        print(f"[es] total documents: {doc_count}")
        if doc_count == 0:
            print("[es] FAIL: index is empty — check sync flags and MySQL queries")

        agg = await es_client_manager.client.search(
            index=idx,
            size=0,
            aggs={"by_column": {"terms": {"field": "column_id", "size": 500}}},
        )
        buckets = agg["aggregations"]["by_column"]["buckets"]
        indexed_columns = {b["key"] for b in buckets}
        print(f"[es] distinct column_id count: {len(indexed_columns)}")

        missing_in_es = sorted(set(sync_column_ids) - indexed_columns)
        extra_in_es = sorted(indexed_columns - set(sync_column_ids))
        if missing_in_es:
            print(f"[es] WARN: {len(missing_in_es)} sync columns not in ES (first 10): {missing_in_es[:10]}")
        if extra_in_es:
            print(f"[es] INFO: {len(extra_in_es)} ES columns not in current sync config")

        top = sorted(buckets, key=lambda b: b["doc_count"], reverse=True)[:5]
        print(f"[es] top columns by doc count: {[(b['key'], b['doc_count']) for b in top]}")

        # recall smoke test
        for keyword in ["北京", "active", "个人"]:
            hits = await value_repo.search(keyword, threshold=0.1, limit=3)
            print(f"[es] search '{keyword}': {len(hits)} hits")
            for h in hits[:2]:
                print(f"       -> {h.get('value')} ({h.get('column_id')})")
    finally:
        await es_client_manager.close()

    # compare MySQL expected vs ES for sync columns
    async with finance_mysql_client_manager.session_factory() as session:
        repo = FinanceMysqlRepository(session)
        expected_docs = 0
        db_missing_cols: list[str] = []
        empty_cols: list[str] = []

        for cid in sync_column_ids:
            table, col = cid.rsplit(".", 1)
            types = await repo.get_column_types(table)
            if col not in types:
                db_missing_cols.append(cid)
                continue
            vals = await repo.get_column_values(table, col, 5000)
            if not vals:
                empty_cols.append(cid)
            expected_docs += len(vals)

        print(f"[mysql] expected documents (sum of distinct values, limit 5000/col): {expected_docs}")
        print(f"[mysql] sync columns missing in DB schema: {len(db_missing_cols)}")
        if db_missing_cols[:5]:
            print(f"        examples: {db_missing_cols[:5]}")
        print(f"[mysql] sync columns with zero values: {len(empty_cols)}")

    await finance_mysql_client_manager.close()

    if doc_count > 0 and len(indexed_columns) > 0:
        ratio = doc_count / expected_docs if expected_docs else 0
        print(f"[summary] ES/MySQL expected ratio: {ratio:.1%}")
        if ratio < 0.5:
            print("[summary] WARN: ES has far fewer docs than MySQL expects — investigate bulk errors")
        else:
            print("[summary] OK: ES index looks populated")


if __name__ == "__main__":
    parser = ArgumentParser(description="Verify ES column-value index")
    parser.add_argument("-c", "--conf", default="conf/meta_config.yaml")
    args = parser.parse_args()
    asyncio.run(verify(Path(args.conf)))
