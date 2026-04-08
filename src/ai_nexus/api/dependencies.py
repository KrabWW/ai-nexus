"""FastAPI 依赖注入：从 app.state 获取 service 实例。"""

from fastapi import Request

from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.services.graph_service import GraphService
from ai_nexus.services.query_service import QueryService


def get_graph_service(request: Request) -> GraphService:
    return request.app.state.graph_service


def get_query_service(request: Request) -> QueryService:
    return request.app.state.query_service


def get_audit_repo(request: Request) -> AuditRepo:
    return request.app.state.audit_repo
