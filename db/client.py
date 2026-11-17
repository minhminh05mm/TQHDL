import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def settings():
    return {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5433")),
        "dbname": os.getenv("PGDATABASE", "btl_tqhdl"),
        "user": os.getenv("PGUSER", "btl_app"),
        "password": os.getenv("PGPASSWORD", ""),
        "sslmode": os.getenv("PGSSLMODE", "prefer"),
        "connect_timeout": 5,
        "application_name": "btl_tqhdl",
    }


def connect(**overrides):
    return psycopg.connect(**(settings() | overrides), row_factory=dict_row)


def create_database():
    config = settings()
    with connect(dbname=os.getenv("PGMAINTENANCE_DB", "postgres"), autocommit=True) as connection:
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (config["dbname"],)).fetchone()
        if not exists:
            connection.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(config["dbname"])))


def initialize(connection):
    connection.execute((Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8"))


def current_run(connection):
    return connection.execute(
        "SELECT run_id, input_fingerprint, finished_at FROM rentals.etl_runs "
        "WHERE status='success' ORDER BY run_id DESC LIMIT 1"
    ).fetchone()


def version():
    with connect() as connection:
        run = current_run(connection)
    if run is None:
        raise ValueError("Chưa có lần ETL thành công. Chạy python etl.py trước.")
    return run["run_id"], run["finished_at"].isoformat()


def read_listings(run_id=None, notebook=False):
    with connect() as connection:
        if run_id is None:
            run = current_run(connection)
            if run is None:
                raise ValueError("Chưa có lần ETL thành công.")
            run_id = run["run_id"]
        query = "SELECT * FROM rentals.v_all_listings WHERE etl_run_id=%s ORDER BY import_position"
        with connection.cursor() as cursor:
            cursor.execute(query, (run_id,))
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
    data = pd.DataFrame(rows, columns=columns).drop(columns=["etl_run_id", "import_position"])
    for column in ["Giá thuê (đồng/tháng)", "Diện tích (m²)", "Giá thuê/m² (đồng/tháng)"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if notebook:
        data = data.dropna(subset=["Diện tích (m²)"])
    return data
