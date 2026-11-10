import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):

    # 讀取資料庫連線設定
    conninfo = make_conninfo(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD")
    )

    # 建立資料庫連線池
    app.state.pool = AsyncConnectionPool(
        conninfo=conninfo,
        kwargs={"row_factory": dict_row},
        open=False
    )

    await app.state.pool.open(wait=True)
    print("✅ PostgreSQL 連線成功")

    try:
        yield
    finally:
        await app.state.pool.close()
        print("🛑 PostgreSQL 連線已關閉")


# 提供資料庫連線給 FastAPI 路由
async def getDB(request: Request):
    async with request.app.state.pool.connection() as conn:
        yield conn