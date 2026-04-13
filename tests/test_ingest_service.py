"""Tests for IngestService.

Tests cover:
- Batch import from Feishu space
- Dry-run mode (no DB writes)
- Incremental import (skip unchanged documents)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_nexus.models.extraction import ExtractedEntity, ExtractedRule, ExtractionResult
from ai_nexus.services.ingest_service import IngestService


class TestIngestService:
    """Test suite for IngestService."""

    @pytest.fixture
    def mock_feishu_proxy(self) -> MagicMock:
        """Mock FeishuProxy."""
        proxy = MagicMock()
        proxy.list_space_docs = AsyncMock(return_value=[
            {"doc_token": "doc1", "title": "Test Doc 1", "type": "docx"},
            {"doc_token": "doc2", "title": "Test Doc 2", "type": "docx"},
        ])
        proxy.get_doc_content = AsyncMock(return_value="Test content with business knowledge.")
        proxy.compute_content_hash = MagicMock(return_value="abc123")
        return proxy

    @pytest.fixture
    def mock_extraction_service(self) -> MagicMock:
        """Mock ExtractionService."""
        service = MagicMock()
        # Use proper Pydantic model instances
        service.extract = AsyncMock(
            return_value=ExtractionResult(
                entities=[
                    ExtractedEntity(
                        name="TestEntity",
                        type="概念",
                        domain="test",
                        confidence=0.9,
                        description="Test",
                    ),
                ],
                relations=[],
                rules=[
                    ExtractedRule(
                        name="TestRule",
                        severity="warning",
                        domain="test",
                        confidence=0.8,
                        description="Test rule",
                    ),
                ],
            ),
        )
        return service

    @pytest.fixture
    def mock_repos(self) -> dict[str, MagicMock]:
        """Mock repositories."""
        entity_repo = MagicMock()
        entity_repo.create = AsyncMock(return_value=MagicMock(id=1))
        entity_repo.search = AsyncMock(return_value=[])
        entity_repo.list = AsyncMock(return_value=[])
        # Mock the database connection
        mock_db = MagicMock()
        mock_db.fetchone = AsyncMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        entity_repo._db = mock_db

        relation_repo = MagicMock()
        relation_repo.create = AsyncMock(return_value=MagicMock(id=1))
        relation_repo._db = mock_db

        rule_repo = MagicMock()
        rule_repo.create = AsyncMock(return_value=MagicMock(id=1))
        rule_repo._db = mock_db

        audit_repo = MagicMock()
        audit_repo.create = AsyncMock(return_value=MagicMock(id=1))

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
        """Create IngestService instance with mocked dependencies."""
        return IngestService(
            feishu_proxy=mock_feishu_proxy,
            extraction_service=mock_extraction_service,
            entity_repo=mock_repos["entity_repo"],
            relation_repo=mock_repos["relation_repo"],
            rule_repo=mock_repos["rule_repo"],
            audit_repo=mock_repos["audit_repo"],
        )

    @pytest.mark.asyncio
    async def test_ingest_space_batch_import(
        self,
        ingest_service: IngestService,
        mock_feishu_proxy: MagicMock,
        mock_extraction_service: MagicMock,
        mock_repos: dict[str, MagicMock],
    ) -> None:
        """Test batch import from Feishu space."""
        # Mock database operations
        with patch.object(ingest_service, "_get_existing_doc", return_value=None):
            with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
                result = await ingest_service.ingest_space(
                    space_id="test_space",
                    domain_hint="test",
                    dry_run=False,
                )

        assert result["total"] == 2
        assert result["processed"] == 2
        assert result["submitted"] == 4  # 1 entity + 1 rule per doc, 2 docs
        assert result["failed"] == 0
        assert len(result["errors"]) == 0

        # Verify Feishu API was called
        mock_feishu_proxy.list_space_docs.assert_called_once_with("test_space")

    @pytest.mark.asyncio
    async def test_ingest_space_dry_run(
        self,
        ingest_service: IngestService,
        mock_feishu_proxy: MagicMock,
        mock_extraction_service: MagicMock,
    ) -> None:
        """Test dry-run mode doesn't write to database."""
        result = await ingest_service.ingest_space(
            space_id="test_space",
            dry_run=True,
        )

        assert result["total"] == 2
        assert result["processed"] == 2
        assert result["submitted"] == 0  # dry-run mode doesn't submit

    @pytest.mark.asyncio
    async def test_ingest_document_basic(
        self,
        ingest_service: IngestService,
        mock_extraction_service: MagicMock,
        mock_repos: dict[str, MagicMock],
    ) -> None:
        """Test basic single document import."""
        with patch.object(ingest_service, "_get_existing_doc", return_value=None):
            with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
                result = await ingest_service.ingest_document(
                    content="Test content with business rules.",
                    title="Test Document",
                    source="manual",
                    domain_hint="test",
                )

        assert not result.get("skipped")
        assert result["submitted"] == 2  # 1 entity + 1 rule
        assert result["status"] == "pending_audit"

        # Verify extraction was called
        mock_extraction_service.extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_document_empty_content(
        self,
        ingest_service: IngestService,
        mock_extraction_service: MagicMock,
    ) -> None:
        """Test import with empty content returns zero counts."""
        result = await ingest_service.ingest_document(
            content="",
            title="Empty Doc",
        )

        assert result["submitted"] == 0
        assert result["status"] == "direct"

        # Extraction should not be called for empty content
        mock_extraction_service.extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_incremental_import_skip_unchanged(
        self,
        ingest_service: IngestService,
        mock_feishu_proxy: MagicMock,
        mock_extraction_service: MagicMock,
    ) -> None:
        """Test that unchanged documents are skipped."""
        existing_doc = {
            "content_hash": "abc123",
            "status": "done",
        }

        # Patch compute_content_hash to return the same hash as existing
        with patch.object(
            ingest_service,
            "_get_existing_doc",
            return_value=existing_doc,
        ):
            with patch(
                "ai_nexus.services.ingest_service.FeishuProxy.compute_content_hash",
                return_value="abc123",
            ):
                result = await ingest_service.ingest_document(
                    content="Unchanged content",
                    title="Test",
                    doc_token="doc1",
                    space_id="space1",
                )

        assert result.get("skipped")
        assert result["submitted"] == 0
        assert result["status"] == "direct"

        # Extraction should not be called for unchanged docs
        mock_extraction_service.extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_incremental_import_reprocess_changed(
        self,
        ingest_service: IngestService,
        mock_feishu_proxy: MagicMock,
        mock_extraction_service: MagicMock,
        mock_repos: dict[str, MagicMock],
    ) -> None:
        """Test that changed documents are re-processed."""
        # Existing doc has different hash
        existing_doc = {
            "content_hash": "old_hash",
            "status": "done",
        }

        with patch.object(
            ingest_service,
            "_get_existing_doc",
            return_value=existing_doc,
        ):
            with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
                result = await ingest_service.ingest_document(
                    content="New content with changes",
                    title="Updated Doc",
                    doc_token="doc1",
                    space_id="space1",
                )

        assert not result.get("skipped")
        assert result["submitted"] == 2  # 1 entity + 1 rule

        # Extraction should be called for changed docs
        mock_extraction_service.extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_space_with_api_error(
        self,
        ingest_service: IngestService,
        mock_feishu_proxy: MagicMock,
    ) -> None:
        """Test batch import handles API errors gracefully."""
        # Make one doc fail
        async def failing_get_doc(token: str) -> str:
            if token == "doc2":
                raise Exception("API Error")
            return "Content"

        mock_feishu_proxy.get_doc_content = AsyncMock(side_effect=failing_get_doc)

        with patch.object(ingest_service, "_get_existing_doc", return_value=None):
            with patch.object(ingest_service, "_update_ingest_tracking", new_callable=AsyncMock):
                result = await ingest_service.ingest_space(
                    space_id="test_space",
                    dry_run=True,
                )

        assert result["total"] == 2
        assert result["failed"] == 1
        assert len(result["errors"]) == 1

    def test_map_entity_names_to_ids(
        self,
        ingest_service: IngestService,
        mock_repos: dict[str, MagicMock],
    ) -> None:
        """Test entity name to ID mapping."""
        # Mock existing entities
        entity1 = MagicMock()
        entity1.name = "ExistingEntity"
        entity1.id = 10

        mock_repos["entity_repo"].list = AsyncMock(return_value=[entity1])
        mock_repos["entity_repo"].search = AsyncMock(return_value=[])

        # Test mapping
        import asyncio

        async def run_test():
            result = await ingest_service._map_entity_names_to_ids(
                entities=[],
                relations=[],
                domain="test",
            )
            assert "ExistingEntity" in result
            assert result["ExistingEntity"] == 10

        asyncio.run(run_test())
