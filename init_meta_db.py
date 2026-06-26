"""初始化 financemeta 元数据库"""
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=False)

DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = int(os.getenv("DB_PORT", ""))
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
META_DB = "financemeta"


def init_meta_db() -> None:
    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{META_DB}` CHARACTER SET utf8mb4")
    conn.close()
    print(f"数据库 {META_DB} 创建完成")

    sql_file = ROOT_DIR / "sql" / "financemeta.sql"
    with open(sql_file, encoding="utf-8-sig") as f:
        sql = f.read()

    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                           database=META_DB, autocommit=True)
    with conn.cursor() as cur:
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt)
    conn.close()
    print(f"数据库 {META_DB} 表结构初始化完成")


if __name__ == "__main__":
    init_meta_db()
