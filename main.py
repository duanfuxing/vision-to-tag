from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from app.routers import video
from app.routers import tasks
from app.services.logger import get_logger
from config import Settings

logger = get_logger()

app = FastAPI(
    title="Vision To Tag API", description="Vision To Tag API service", version="1.0.0"
)

app.include_router(video.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")

# 自定义异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)},
    )

# 处理 HTTPException
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )

if __name__ == "__main__":
    import uvicorn

    port = int(Settings.API_PORT)
    uvicorn.run("main:app", host=Settings.API_HOST, port=port)
