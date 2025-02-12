from fastapi import FastAPI
from app.routers import video
import os

app = FastAPI(
    title="Vision To Tag API", description="Vision To Tag API service", version="1.0.0"
)

app.include_router(video.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))  # 默认使用8000端口
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
