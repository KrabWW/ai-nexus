"""AI Nexus FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_nexus.config import Settings
from ai_nexus.db.sqlite import Database
from ai_nexus.mcp.server import init_services, mcp
from ai_nexus.proxy.mem0_proxy import Mem0Proxy
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.graph_service import GraphService
from ai_nexus.services.query_service import QueryService

settings = Settings()


@asynccontextmanager
async def db_lifespan(app: FastAPI):
    """初始化 SQLite 连接，运行迁移，初始化 services，关闭时断开连接。"""
    db = Database(settings.sqlite_path)
    await db.connect()
    await db.run_migrations()
    app.state.db = db

    # 初始化 repos
    entity_repo = EntityRepo(db)
    relation_repo = RelationRepo(db)
    rule_repo = RuleRepo(db)
    audit_repo = AuditRepo(db)

    # 初始化 proxy 和 services
    mem0_proxy = Mem0Proxy(base_url=settings.mem0_api_url)
    graph_service = GraphService(entity_repo, relation_repo, rule_repo)
    query_service = QueryService(graph_service, mem0_proxy)

    # 注入到 app.state 和 MCP server
    app.state.graph_service = graph_service
    app.state.query_service = query_service
    app.state.audit_repo = audit_repo
    init_services(graph_service, query_service)

    yield

    await db.disconnect()


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    # MCP Streamable HTTP transport app
    mcp_http_app = mcp.streamable_http_app()

    # 组合两个 lifespan（DB + MCP）
    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        async with db_lifespan(app):
            async with mcp_http_app.router.lifespan_context(app):
                yield

    app = FastAPI(
        title="AI Nexus",
        description="AI Business Knowledge OS",
        version="0.1.0",
        lifespan=combined_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/mcp", mcp_http_app)

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
