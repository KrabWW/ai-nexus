"""FastAPI 依赖注入：从 app.state 获取 service 实例。"""

from fastapi import Request

from ai_nexus.extraction.extraction_service import ExtractionService
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.code_reference_repo import CodeReferenceRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.graph_service import GraphService
from ai_nexus.services.query_service import QueryService


def get_graph_service(request: Request) -> GraphService:
    return request.app.state.graph_service


def get_query_service(request: Request) -> QueryService:
    return request.app.state.query_service


def get_audit_repo(request: Request) -> AuditRepo:
    return request.app.state.audit_repo


def get_entity_repo(request: Request) -> EntityRepo:
    return request.app.state.graph_service._entities


def get_rule_repo(request: Request) -> RuleRepo:
    return request.app.state.graph_service._rules


def get_relation_repo(request: Request) -> RelationRepo:
    return request.app.state.graph_service._relations


def get_extraction_service(request: Request) -> ExtractionService:
    return request.app.state.extraction_service


def get_code_reference_repo(request: Request) -> CodeReferenceRepo:
    return request.app.state.code_reference_repo
