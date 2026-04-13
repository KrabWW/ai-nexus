"""IngestService — 文档导入流程编排服务。

负责从飞书知识库批量导入文档，调用 ExtractionEngine 进行知识提取，
并将提取结果提交到审核工作流。
"""

import logging
from typing import Any

from ai_nexus.extraction.extraction_service import ExtractionService
from ai_nexus.models.audit import AuditLogCreate
from ai_nexus.proxy.feishu_proxy import FeishuProxy
from ai_nexus.repos.audit_repo import AuditRepo
from ai_nexus.repos.entity_repo import EntityRepo
from ai_nexus.repos.relation_repo import RelationRepo
from ai_nexus.repos.rule_repo import RuleRepo

logger = logging.getLogger(__name__)


class IngestService:
    """文档导入服务，编排飞书读取、知识提取和审核提交流程。

    支持功能：
    - 批量导入飞书知识空间文档
    - 单文档文本导入
    - 增量导入（基于内容哈希跳过未变更文档）
    - Dry-run 模式（提取但不写入数据库）
    """

    def __init__(
        self,
        feishu_proxy: FeishuProxy,
        extraction_service: ExtractionService,
        entity_repo: EntityRepo,
        relation_repo: RelationRepo,
        rule_repo: RuleRepo,
        audit_repo: AuditRepo,
    ) -> None:
        """初始化导入服务。

        Args:
            feishu_proxy: 飞书 API 代理
            extraction_service: 知识提取服务
            entity_repo: 实体仓储
            relation_repo: 关系仓储
            rule_repo: 规则仓储
            audit_repo: 审核日志仓储
        """
        self._feishu = feishu_proxy
        self._extraction = extraction_service
        self._entities = entity_repo
        self._relations = relation_repo
        self._rules = rule_repo
        self._audit = audit_repo

    async def ingest_space(
        self,
        space_id: str,
        domain_hint: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """从飞书知识空间批量导入文档。

        Args:
            space_id: 飞书知识空间 ID
            domain_hint: 可选的业务领域提示
            dry_run: 是否为 dry-run 模式（不写入数据库）

        Returns:
            导入结果统计:
            - total: 总文档数
            - skipped: 跳过的文档数（内容未变更）
            - processed: 处理的文档数
            - entities: 提取的实体总数
            - relations: 提取的关系总数
            - rules: 提取的规则总数
            - failed: 失败的文档数
        """
        docs = await self._feishu.list_space_docs(space_id)

        total = len(docs)
        skipped = 0
        processed = 0
        failed = 0
        total_submitted = 0
        errors: list[str] = []

        for doc in docs:
            doc_token = doc.get("doc_token")
            doc_title = doc.get("title", "")

            try:
                result = await self.ingest_document(
                    content="",  # Will be fetched from Feishu
                    title=doc_title,
                    source=f"feishu:{space_id}",
                    domain_hint=domain_hint,
                    dry_run=dry_run,
                    doc_token=doc_token,
                    space_id=space_id,
                )

                if result.get("skipped"):
                    skipped += 1
                else:
                    processed += 1
                    total_submitted += result.get("submitted", 0)

            except Exception as e:
                failed += 1
                error_msg = f"Failed to import doc '{doc_title}': {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return {
            "total": total,
            "skipped": skipped,
            "processed": processed,
            "submitted": total_submitted,
            "failed": failed,
            "errors": errors,
        }

    async def ingest_document(
        self,
        content: str,
        title: str,
        source: str = "manual",
        domain_hint: str | None = None,
        dry_run: bool = False,
        doc_token: str | None = None,
        space_id: str | None = None,
    ) -> dict[str, Any]:
        """导入单个文档。

        Args:
            content: 文档内容（如果为空且提供了 doc_token，将从飞书获取）
            title: 文档标题
            source: 来源标识
            domain_hint: 可选的业务领域提示
            dry_run: 是否为 dry-run 模式
            doc_token: 可选的飞书文档 token（用于增量导入）
            space_id: 可选的飞书空间 ID（用于增量导入）

        Returns:
            导入结果:
            - skipped: 是否跳过（内容未变更）
            - entities: 提取的实体数
            - relations: 提取的关系数
            - rules: 提取的规则数
        """
        # Fetch content from Feishu if not provided
        if not content and doc_token:
            content = await self._feishu.get_doc_content(doc_token)

        if not content:
            return {"skipped": False, "submitted": 0, "status": "direct"}

        # Compute content hash for incremental import
        content_hash = FeishuProxy.compute_content_hash(content)

        # Check if document was already imported (only for Feishu sources)
        if doc_token and space_id:
            existing = await self._get_existing_doc(space_id, doc_token)
            if existing and existing.get("content_hash") == content_hash:
                logger.info("Skipping unchanged document: %s", title)
                return {"skipped": True, "submitted": 0, "status": "direct"}

        # Extract knowledge from content
        result = await self._extraction.extract(content, domain_hint=domain_hint)

        if result.is_empty():
            logger.info("No business knowledge extracted from: %s", title)

        if dry_run:
            return {
                "skipped": False,
                "entities": len(result.entities),
                "relations": len(result.relations),
                "rules": len(result.rules),
                "extracted": result.model_dump(),
            }

        # Submit through audit log for review
        extraction_data = result.model_dump()
        source_type = "feishu" if space_id else "document"
        await self._audit.create(AuditLogCreate(
            table_name="knowledge_audit_log",
            record_id=0,
            action="submit_candidate",
            new_value={**extraction_data, "_meta": {"source": source_type, "confidence": 0.7}},
            source_context={
                "source_type": source_type,
                "space_id": space_id,
                "document_title": title,
                "original_text": content[:500] if content else None,
            },
        ))

        # Update ingest tracking for Feishu documents
        if doc_token and space_id:
            await self._update_ingest_tracking(
                space_id=space_id,
                doc_token=doc_token,
                doc_title=title,
                content_hash=content_hash,
                entities_count=len(result.entities),
                relations_count=len(result.relations),
                rules_count=len(result.rules),
            )

        return {
            "submitted": result.count_total(),
            "status": "pending_audit",
        }

    async def _get_existing_doc(self, space_id: str, doc_token: str) -> dict[str, Any] | None:
        """查询已有的文档导入记录。

        Args:
            space_id: 飞书空间 ID
            doc_token: 文档 token

        Returns:
            已有的导入记录，如果不存在则返回 None
        """
        from ai_nexus.db.sqlite import Database

        # Get the database from the entity repo
        db: Database = self._entities._db

        row = await db.fetchone(
            """SELECT id, space_id, doc_token, doc_title, content_hash, status,
                      entities_count, relations_count, rules_count, last_imported_at
               FROM ingest_tracking
               WHERE space_id = ? AND doc_token = ?""",
            (space_id, doc_token),
        )

        if row:
            return {
                "id": row[0],
                "space_id": row[1],
                "doc_token": row[2],
                "doc_title": row[3],
                "content_hash": row[4],
                "status": row[5],
                "entities_count": row[6],
                "relations_count": row[7],
                "rules_count": row[8],
                "last_imported_at": row[9],
            }
        return None

    async def _update_ingest_tracking(
        self,
        space_id: str,
        doc_token: str,
        doc_title: str,
        content_hash: str,
        entities_count: int,
        relations_count: int,
        rules_count: int,
    ) -> None:
        """更新文档导入追踪记录。

        Args:
            space_id: 飞书空间 ID
            doc_token: 文档 token
            doc_title: 文档标题
            content_hash: 内容哈希值
            entities_count: 提取的实体数
            relations_count: 提取的关系数
            rules_count: 提取的规则数
        """
        from ai_nexus.db.sqlite import Database

        db: Database = self._entities._db

        # Try to update existing record
        existing = await self._get_existing_doc(space_id, doc_token)

        if existing:
            await db.execute(
                """UPDATE ingest_tracking
                   SET doc_title = ?, content_hash = ?, status = 'pending_audit',
                       entities_count = ?, relations_count = ?, rules_count = ?,
                       last_imported_at = CURRENT_TIMESTAMP
                   WHERE space_id = ? AND doc_token = ?""",
                (
                    doc_title,
                    content_hash,
                    entities_count,
                    relations_count,
                    rules_count,
                    space_id,
                    doc_token,
                ),
            )
        else:
            await db.execute(
                """INSERT INTO ingest_tracking
                   (space_id, doc_token, doc_title, content_hash, status,
                    entities_count, relations_count, rules_count)
                   VALUES (?, ?, ?, ?, 'pending_audit', ?, ?, ?)""",
                (
                    space_id,
                    doc_token,
                    doc_title,
                    content_hash,
                    entities_count,
                    relations_count,
                    rules_count,
                ),
            )

    async def _map_entity_names_to_ids(
        self,
        entities: list,
        relations: list,
        domain: str,
    ) -> dict[str, int]:
        """将实体名称映射到数据库 ID。

        用于创建关系时查找源实体和目标实体的 ID。

        Args:
            entities: 提取的实体列表
            relations: 提取的关系列表
            domain: 业务领域

        Returns:
            实体名称到 ID 的映射字典
        """
        name_to_id: dict[str, int] = {}

        # First, get all entities from this domain
        existing_entities = await self._entities.list(domain=domain, limit=1000)
        for entity in existing_entities:
            name_to_id[entity.name] = entity.id

        # Add newly created entities (they should be in the database by now)
        for entity in entities:
            if entity.name not in name_to_id:
                # Try to find the entity by name
                found = await self._entities.search(entity.name, domain=domain, limit=1)
                if found:
                    name_to_id[entity.name] = found[0].id

        # Also check relation source/target names
        for relation in relations:
            if relation.source_name and relation.source_name not in name_to_id:
                found = await self._entities.search(relation.source_name, domain=domain, limit=1)
                if found:
                    name_to_id[relation.source_name] = found[0].id

            if relation.target_name and relation.target_name not in name_to_id:
                found = await self._entities.search(relation.target_name, domain=domain, limit=1)
                if found:
                    name_to_id[relation.target_name] = found[0].id

        return name_to_id
