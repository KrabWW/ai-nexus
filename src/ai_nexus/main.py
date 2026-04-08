"""AI Nexus FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_nexus.config import Settings
from ai_nexus.db.sqlite import Database
from ai_nexus.mcp.server import mcp

settings = Settings()


@asynccontextmanager
async def db_lifespan(app: FastAPI):
    """初始化 SQLite 连接，运行迁移，关闭时断开连接。"""
    db = Database(settings.sqlite_path)
    await db.connect()
    await db.run_migrations()
    app.state.db = db
    yield
    await db.disconnect()


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    app = FastAPI(
        title="AI Nexus",
        description="AI Business Knowledge OS",
        version="0.1.0",
        lifespan=db_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/mcp", mcp.streamable_http_app())

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
