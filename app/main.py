import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import query as query_router
from app.core.context import request_id_ctx_var
from app.core.lifespan import lifespan
from app.core.log import logger

STATIC_DIR = Path(__file__).parents[1] / "static"

app = FastAPI(
    title="Finance Agent - 金融问数",
    description="基于 NL2SQL 的金融智能数据查询服务",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request_id_ctx_var.set(request_id)
    logger.info(f"[{request.method}] {request.url.path}")
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未捕获异常: {exc}")
    return JSONResponse(status_code=500, content={"error": str(exc)})


app.include_router(query_router.router, prefix="/api/v1", tags=["查询"])


@app.get("/", include_in_schema=False)
async def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return JSONResponse({"message": "Finance Agent API", "docs": "/docs"})


@app.get("/health", tags=["健康检查"])
async def health():
    return {"status": "ok"}
