"""Ingest API router — 文档导入 REST API 端点。

提供飞书文档批量导入和单文档导入的 REST API 接口。
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ai_nexus.api.dependencies import (
    get_audit_repo,
    get_entity_repo,
    get_relation_repo,
    get_rule_repo,
)
from ai_nexus.config import Settings
from ai_nexus.extraction.extraction_service import ExtractionService
from ai_nexus.proxy.feishu_proxy import FeishuProxy
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo
from ai_nexus.services.ingest_service import IngestService

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


# --- Request/Response Models ---


class FeishuIngestRequest(BaseModel):
    """飞书空间批量导入请求。

    Attributes:
        space_id: 飞书知识空间 ID
        domain_hint: 可选的业务领域提示
        dry_run: 是否为 dry-run 模式（不写入数据库）
    """

    space_id: str
    domain_hint: str | None = None
    dry_run: bool = False


class DocumentIngestRequest(BaseModel):
    """单文档导入请求。

    Attributes:
        content: 文档内容
        title: 文档标题
        source: 来源标识（默认为 "manual"）
        domain_hint: 可选的业务领域提示
        dry_run: 是否为 dry-run 模式
    """

    content: str
    title: str
    source: str = "manual"
    domain_hint: str | None = None
    dry_run: bool = False


class IngestResult(BaseModel):
    """导入结果。

    Attributes:
        total: 总文档数（批量导入时）
        processed: 处理的文档数
        skipped: 跳过的文档数（内容未变更）
        submitted: 提交到审核队列的知识条目数
        audit_status: 审核状态（"pending_audit" 或 "direct"）
        failed: 失败的文档数
        errors: 错误信息列表
    """

    total: int = 0
    processed: int = 0
    skipped: int = 0
    submitted: int = 0
    audit_status: str = "direct"
    failed: int = 0
    errors: list[str] = []


# --- Dependencies ---


def get_settings() -> Settings:
    """获取应用配置。"""
    from ai_nexus.config import Settings

    return Settings()


def get_feishu_proxy(settings: Annotated[Settings, Depends(get_settings)]) -> FeishuProxy:
    """获取飞书代理实例。"""
    return FeishuProxy(
        app_id=settings.feishu_app_id,
        app_secret=settings.feishu_app_secret,
        base_url=settings.feishu_base_url,
    )


def get_extraction_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExtractionService:
    """获取知识提取服务实例。"""
    return ExtractionService(api_key=settings.anthropic_api_key)


def get_ingest_service(
    feishu_proxy: Annotated[FeishuProxy, Depends(get_feishu_proxy)],
    extraction_service: Annotated[ExtractionService, Depends(get_extraction_service)],
    entity_repo: Annotated[EntityRepo, Depends(get_entity_repo)],
    relation_repo: Annotated[RelationRepo, Depends(get_relation_repo)],
    rule_repo: Annotated[RuleRepo, Depends(get_rule_repo)],
    audit_repo: Annotated[AuditRepo, Depends(get_audit_repo)],
) -> IngestService:
    """获取文档导入服务实例。"""
    return IngestService(
        feishu_proxy=feishu_proxy,
        extraction_service=extraction_service,
        entity_repo=entity_repo,
        relation_repo=relation_repo,
        rule_repo=rule_repo,
        audit_repo=audit_repo,
    )


# --- API Endpoints ---


@router.post("/feishu", response_model=IngestResult, status_code=status.HTTP_200_OK)
async def ingest_from_feishu(
    request: FeishuIngestRequest,
    ingest_service: Annotated[IngestService, Depends(get_ingest_service)],
) -> IngestResult:
    """从飞书知识空间批量导入文档。

    执行流程：
    1. 列出空间中的所有文档
    2. 对每个文档：
       - 检查内容哈希，跳过未变更的文档
       - 调用 ExtractionEngine 提取知识
       - 将提取结果提交到审核工作流
    3. 返回导入统计结果

    Args:
        request: 导入请求参数
        ingest_service: 文档导入服务

    Returns:
        导入结果统计
    """
    try:
        result = await ingest_service.ingest_space(
            space_id=request.space_id,
            domain_hint=request.domain_hint,
            dry_run=request.dry_run,
        )
        return IngestResult(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Feishu import failed: {e}",
        ) from e


@router.post("/document", response_model=IngestResult, status_code=status.HTTP_200_OK)
async def ingest_document(
    request: DocumentIngestRequest,
    ingest_service: Annotated[IngestService, Depends(get_ingest_service)],
) -> IngestResult:
    """导入单个文档。

    直接从提供的文本内容中提取业务知识并提交到审核工作流。

    Args:
        request: 文档导入请求
        ingest_service: 文档导入服务

    Returns:
        导入结果统计
    """
    try:
        result = await ingest_service.ingest_document(
            content=request.content,
            title=request.title,
            source=request.source,
            domain_hint=request.domain_hint,
            dry_run=request.dry_run,
        )
        return IngestResult(
            total=1,
            processed=0 if result.get("skipped") else 1,
            skipped=1 if result.get("skipped") else 0,
            submitted=result.get("submitted", 0),
            audit_status=result.get("status", "direct"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document import failed: {e}",
        ) from e


@router.get("/health", status_code=status.HTTP_200_OK)
async def ingest_health(
    feishu_proxy: Annotated[FeishuProxy, Depends(get_feishu_proxy)],
) -> dict[str, Any]:
    """检查导入服务健康状态。

    Returns:
        健康状态信息
    """
    feishu_available = await feishu_proxy.is_available()

    return {
        "status": "healthy" if feishu_available else "degraded",
        "feishu_available": feishu_available,
    }
