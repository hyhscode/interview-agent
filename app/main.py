import logging
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="上传简历 + JD → 匹配度分析 → 模拟面试 → 面经检索",
    version = "0.1.0",
)

@app.middleware("http")
async def request_context(request:Request,call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
    start = time.perf_counter()
                                                                         
    try:
        response = await call_next(request)

    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000

        logger.exception(
            "rid=%s %s %s -> 500(%.1fms)%s",
            request_id, request.method,request.url.path,elapsed,exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail":"服务器内部错误","request_id":request_id},
        )
    elapsed = (time.perf_counter() - start)* 1000

    logger.info(
        "rid=%s %s %s -> %s (%.1fms)",
        request_id, request.method, request.url.path,
        response.status_code, elapsed,
    )

    response.headers["X-Request-ID"] = request_id

    return response

@app.get("/healthz")
async def healthz():
    return{"status":"ok","env":settings.app_env}