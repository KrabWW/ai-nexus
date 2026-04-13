"""AI Nexus FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai_nexus.api.console_router import router as console_router
from ai_nexus.api.graph_router import router as graph_router
from ai_nexus.api.ingest_router import router as ingest_router
from ai_nexus.api.lint_router import router as lint_router
from ai_nexus.api.router import router as api_router
from ai_nexus.api.violations_router import router as violations_router
from ai_nexus.config import Settings
from ai_nexus.db.sqlite import Database
from ai_nexus.mcp.server import init_services, mcp
from ai_nexus.proxy.mem0_proxy import Mem0Proxy
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.code_reference_repo import CodeReferenceRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.repos.violation_repo import ViolationRepo
from ai_nexus.services.extraction_service import ExtractionService
from ai_nexus.services.flywheel_service import FlywheelService
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

    # 初始化 violation repo, code reference repo 和 flywheel service
    violation_repo = ViolationRepo(db)
    code_reference_repo = CodeReferenceRepo(db)
    flywheel_service = FlywheelService(rule_repo, violation_repo)

    # 初始化 extraction service
    extraction_service = ExtractionService(
        entity_repo, relation_repo, rule_repo,
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
    )

    # 注入到 app.state 和 MCP server
    app.state.graph_service = graph_service
    app.state.query_service = query_service
    app.state.audit_repo = audit_repo
    app.state.violation_repo = violation_repo
    app.state.code_reference_repo = code_reference_repo
    app.state.flywheel_service = flywheel_service
    app.state.extraction_service = extraction_service
    init_services(graph_service, query_service, audit_repo)

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

    # Include REST API routers
    app.include_router(api_router)
    app.include_router(lint_router)
    app.include_router(graph_router)
    app.include_router(ingest_router)
    app.include_router(violations_router)
    app.include_router(console_router)

    # Mount static files for graph visualization
    static_dir = Path(__file__).parent.parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Mount MCP separately (outside lifespan for test compatibility)
    mcp_http_app = mcp.streamable_http_app()
    app.mount("/mcp", mcp_http_app)

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
