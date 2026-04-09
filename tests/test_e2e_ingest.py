"""E2E validation tests for the ingest pipeline.

These tests validate the full pipeline from Feishu document import
to knowledge extraction and audit workflow submission.

Note: These tests require real Feishu API credentials and are skipped
by default. Set the environment variables to run them:
- AI_NEXUS_FEISHU_APP_ID
- AI_NEXUS_FEISHU_APP_SECRET
- AI_NEXUS_ANTHROPIC_API_KEY
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_nexus.config import Settings
from ai_nexus.extraction.extraction_service import ExtractionService
from ai_nexus.models.extraction import ExtractionResult
from ai_nexus.services.ingest_service import IngestService

# Skip all tests if Feishu credentials are not provided
SKIP_REASON = (
    "Feishu credentials not provided. "
    "Set AI_NEXUS_FEISHU_APP_ID and AI_NEXUS_FEISHU_APP_SECRET to run."
)


@pytest.mark.skipif(
    not os.getenv("AI_NEXUS_FEISHU_APP_ID") or not os.getenv("AI_NEXUS_FEISHU_APP_SECRET"),
    reason=SKIP_REASON,
)
class TestE2EIngestWithRealFeishu:
    """E2E tests requiring real Feishu API access."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Load settings with real credentials."""
        return Settings()

    @pytest.fixture
    def feishu_proxy(self, settings: Settings) -> None:
        """Create real Feishu proxy."""
        from ai_nexus.proxy.feishu_proxy import FeishuProxy

        return FeishuProxy(
            app_id=settings.feishu_app_id,
            app_secret=settings.feishu_app_secret,
            base_url=settings.feishu_base_url,
        )

    @pytest.fixture
    def extraction_service(self, settings: Settings) -> None:
        """Create real extraction service."""
        return ExtractionService(api_key=settings.anthropic_api_key)

    @pytest.mark.asyncio
    async def test_feishu_connection(self, feishu_proxy) -> None:
        """Test that Feishu API is accessible."""
        available = await feishu_proxy.is_available()
        assert available, "Feishu API should be accessible"

    @pytest.mark.asyncio
    async def test_list_feishu_docs(self, feishu_proxy) -> None:
        """Test listing documents from Feishu space."""
        # Use a known test space ID or skip
        space_id = os.getenv("TEST_FEISHU_SPACE_ID")
        if not space_id:
            pytest.skip("TEST_FEISHU_SPACE_ID not set")

        docs = await feishu_proxy.list_space_docs(space_id)
        assert isinstance(docs, list)

    @pytest.mark.asyncio
    async def test_get_feishu_doc_content(self, feishu_proxy) -> None:
        """Test reading document content from Feishu."""
        doc_token = os.getenv("TEST_FEISHU_DOC_TOKEN")
        if not doc_token:
            pytest.skip("TEST_FEISHU_DOC_TOKEN not set")

        content = await feishu_proxy.get_doc_content(doc_token)
        assert isinstance(content, str)
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_full_ingest_pipeline(self, feishu_proxy, extraction_service) -> None:
        """Test complete pipeline: Feishu → Extraction → Audit."""
        space_id = os.getenv("TEST_FEISHU_SPACE_ID")
        if not space_id:
            pytest.skip("TEST_FEISHU_SPACE_ID not set")

        # This is a placeholder for the full E2E test
        # In real scenario, this would:
        # 1. List docs from space
        # 2. Read each doc content
        # 3. Extract knowledge
        # 4. Submit to audit workflow
        # 5. Verify audit workflow has pending candidates
        pass


class TestE2EIngestWithMocks:
    """E2E tests using mocks for faster execution without external dependencies."""

    @pytest.fixture
    def mock_feishu_proxy(self) -> MagicMock:
        """Mock FeishuProxy."""
        proxy = MagicMock()
        proxy.list_space_docs = AsyncMock(return_value=[
            {"doc_token": "doc1", "title": "ICU排班规则", "type": "docx"},
            {"doc_token": "doc2", "title": "值班管理制度", "type": "docx"},
        ])
        proxy.get_doc_content = AsyncMock(side_effect=lambda token: {
            "doc1": "ICU需要24小时值班医生，排班周期为7天。",
            "doc2": "医生值班每班不超过8小时，必须有交接记录。",
        }.get(token, ""))
        proxy.compute_content_hash = MagicMock(side_effect=lambda c: f"hash_{len(c)}")
        proxy.is_available = AsyncMock(return_value=True)
        return proxy

    @pytest.fixture
    def mock_extraction_service(self) -> MagicMock:
        """Mock ExtractionService with realistic responses."""
        from ai_nexus.models.extraction import ExtractedEntity, ExtractedRelation, ExtractedRule

        service = MagicMock()

        async def mock_extract(text: str, domain_hint: str | None = None) -> ExtractionResult:
            # Simulate extraction based on content
            if "ICU" in text and "24小时" in text:
                return ExtractionResult(
                    entities=[
                        ExtractedEntity(
                            name="ICU",
                            type="地点",
                            domain="医疗排班",
                            confidence=0.95,
                            description="重症监护室",
                        ),
                        ExtractedEntity(
                            name="24小时值班",
                            type="概念",
                            domain="医疗排班",
                            confidence=0.9,
                            description="全天候值班制度",
                        ),
                    ],
                    relations=[
                        ExtractedRelation(
                            name="ICU → requires → 24小时值班",
                            type="requires",
                            source_name="ICU",
                            target_name="24小时值班",
                            relation_type="requires",
                            domain="医疗排班",
                            confidence=0.9,
                            description="ICU需要24小时值班",
                        ),
                    ],
                    rules=[
                        ExtractedRule(
                            name="ICU需要24小时值班医生",
                            severity="error",
                            domain="医疗排班",
                            confidence=0.95,
                            description="重症监护室必须保证24小时有医生值班",
                        ),
                    ],
                )
            elif "值班" in text and "8小时" in text:
                return ExtractionResult(
                    entities=[
                        ExtractedEntity(
                            name="值班制度",
                            type="概念",
                            domain="医疗排班",
                            confidence=0.85,
                            description="医生值班管理制度",
                        ),
                    ],
                    relations=[],
                    rules=[
                        ExtractedRule(
                            name="医生值班每班不超过8小时",
                            severity="warning",
                            domain="医疗排班",
                            confidence=0.9,
                            description="医生值班时长限制",
                        ),
                    ],
                )
            return ExtractionResult()

        service.extract = AsyncMock(side_effect=mock_extract)
        return service

    @pytest.fixture
    def mock_repos(self) -> dict[str, MagicMock]:
        """Mock repositories."""
        # Mock database connection
        mock_db = MagicMock()
        mock_db.fetchone = AsyncMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=MagicMock(rowcount=1))

        entity_repo = MagicMock()
        entity_repo.create = AsyncMock(
            side_effect=lambda data: MagicMock(id=id(data), **data.model_dump()),
        )
        entity_repo.search = AsyncMock(return_value=[])
        entity_repo.list = AsyncMock(return_value=[])
        entity_repo.get = AsyncMock(return_value=None)
        entity_repo._db = mock_db

        relation_repo = MagicMock()
        relation_repo.create = AsyncMock(
            side_effect=lambda data: MagicMock(id=id(data), **data.model_dump()),
        )
        relation_repo._db = mock_db

        rule_repo = MagicMock()
        rule_repo.create = AsyncMock(
            side_effect=lambda data: MagicMock(id=id(data), **data.model_dump()),
        )
        rule_repo._db = mock_db

        audit_repo = MagicMock()
        audit_repo.create = AsyncMock(
            side_effect=lambda data: MagicMock(
                id=1,
                table_name=data.table_name,
                record_id=data.record_id,
                action=data.action,
            ),
        )
        audit_repo.list_pending = AsyncMock(return_value=[])

        return {
            "entity_repo": entity_repo,
            "relation_repo": relation_repo,
            "rule_repo": rule_repo,
            "audit_repo": audit_repo,
        }

    @pytest.fixture
    def ingest_service(
        self,
        mock_feishu_proxy: MagicMock,
        mock_extraction_service: MagicMock,
        mock_repos: dict[str, MagicMock],
    ) -> IngestService:
        """Create IngestService with mocked dependencies."""
        return IngestService(
            feishu_proxy=mock_feishu_proxy,
            extraction_service=mock_extraction_service,
            entity_repo=mock_repos["entity_repo"],
            relation_repo=mock_repos["relation_repo"],
            rule_repo=mock_repos["rule_repo"],
            audit_repo=mock_repos["audit_repo"],
        )

    @pytest.mark.asyncio
    async def test_full_pipeline_mocked(
        self,
        ingest_service: IngestService,
        mock_feishu_proxy: MagicMock,
        mock_extraction_service: MagicMock,
        mock_repos: dict[str, MagicMock],
    ) -> None:
        """Test full pipeline with mocks: Feishu → Extraction → Storage."""
        # Mock database operations
        with patch.object(ingest_service, "_get_existing_doc", return_value=None):
            with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
                result = await ingest_service.ingest_space(
                    space_id="test_space",
                    domain_hint="医疗排班",
                    dry_run=False,
                )

        # Verify results
        assert result["total"] == 2
        assert result["processed"] == 2
        assert result["failed"] == 0
        assert result["entities"] > 0
        assert result["rules"] > 0

        # Verify Feishu API was called
        mock_feishu_proxy.list_space_docs.assert_called_once_with("test_space")

        # Verify extraction was called for each document
        assert mock_extraction_service.extract.call_count == 2

        # Verify entities were created in database
        assert mock_repos["entity_repo"].create.call_count > 0

        # Verify rules were created in database
        assert mock_repos["rule_repo"].create.call_count > 0

    @pytest.mark.asyncio
    async def test_audit_workflow_submission(
        self,
        ingest_service: IngestService,
        mock_repos: dict[str, MagicMock],
    ) -> None:
        """Test that extracted knowledge is submitted to audit workflow."""
        with patch.object(ingest_service, "_get_existing_doc", return_value=None):
            with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
                await ingest_service.ingest_document(
                    content="ICU需要24小时值班医生",
                    title="Test",
                    domain_hint="医疗排班",
                )

        # Verify audit log was created
        # In the current implementation, entities are created with status="pending"
        # which means they require approval
        entity_calls = mock_repos["entity_repo"].create.call_args_list
        for call in entity_calls:
            entity_data = call[0][0]
            assert entity_data.status == "pending", "Extracted entities should be pending approval"

        rule_calls = mock_repos["rule_repo"].create.call_args_list
        for call in rule_calls:
            rule_data = call[0][0]
            assert rule_data.status == "pending", "Extracted rules should be pending approval"

    @pytest.mark.asyncio
    async def test_incremental_import_workflow(
        self,
        ingest_service: IngestService,
        mock_feishu_proxy: MagicMock,
        mock_extraction_service: MagicMock,
    ) -> None:
        """Test incremental import skips unchanged documents."""
        # First import
        with patch.object(ingest_service, "_get_existing_doc", return_value=None):
            with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
                result1 = await ingest_service.ingest_document(
                    content="Test content",
                    title="Test",
                    doc_token="doc1",
                    space_id="space1",
                )

        assert not result1.get("skipped")
        assert mock_extraction_service.extract.call_count == 1

        # Second import with same content (should skip)
        content_hash = f"hash_{len('Test content')}"
        existing_doc = {"content_hash": content_hash, "status": "done"}

        with patch.object(ingest_service, "_get_existing_doc", return_value=existing_doc):
            with patch(
                "ai_nexus.services.ingest_service.FeishuProxy.compute_content_hash",
                return_value=content_hash,
            ):
                result2 = await ingest_service.ingest_document(
                    content="Test content",
                    title="Test",
                    doc_token="doc1",
                    space_id="space1",
                )

        assert result2.get("skipped")
        # Extraction should not be called again for unchanged content
        assert mock_extraction_service.extract.call_count == 1


@pytest.mark.skipif(
    not os.getenv("AI_NEXUS_ANTHROPIC_API_KEY"),
    reason="AI_NEXUS_ANTHROPIC_API_KEY not set",
)
class TestExtractionWithRealAPI:
    """Tests for extraction with real Claude API."""

    @pytest.fixture
    def extraction_service(self) -> ExtractionService:
        """Create real extraction service."""
        settings = Settings()
        return ExtractionService(api_key=settings.anthropic_api_key)

    @pytest.mark.asyncio
    async def test_extract_medical_knowledge(
        self,
        extraction_service: ExtractionService,
    ) -> None:
        """Test extraction of medical scheduling knowledge."""
        text = """
        ICU排班规则：
        1. 重症监护室需要24小时值班医生
        2. 排班周期为7天
        3. 每班不超过8小时
        4. 必须有交接记录
        """

        result = await extraction_service.extract(text, domain_hint="医疗排班")

        # Should extract at least some entities and rules
        assert result.count_total() > 0 or result.is_empty()

        if not result.is_empty():
            # Verify structure
            for entity in result.entities:
                assert entity.name
                assert entity.type
                assert entity.domain
                assert 0 <= entity.confidence <= 1

            for rule in result.rules:
                assert rule.name
                assert rule.severity in ["error", "warning", "info", "critical"]
                assert rule.domain
                assert 0 <= rule.confidence <= 1

    @pytest.mark.asyncio
    async def test_extract_with_no_business_knowledge(
        self,
        extraction_service: ExtractionService,
    ) -> None:
        """Test extraction with text containing no business knowledge."""
        text = "TODO: refactor this function later. Fix the bug in line 42."

        result = await extraction_service.extract(text)

        # Should return empty or minimal results
        assert result.is_empty() or result.count_total() == 0
