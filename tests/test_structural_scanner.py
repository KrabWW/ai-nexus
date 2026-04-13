"""Tests for structural scanner, MCP tools, and /api/structural-scan endpoint."""

import json

import pytest
from fastapi.testclient import TestClient

from ai_nexus.main import app
from ai_nexus.services.structural_scanner import (
    FileScanResult,
    StructuralScanner,
    _detect_language,
)

# ── StructuralScanner unit tests ─────────────────────────────────────────


class TestDetectLanguage:
    def test_python(self):
        assert _detect_language("foo.py") == "python"

    def test_typescript(self):
        assert _detect_language("app.tsx") == "tsx"

    def test_unknown(self):
        assert _detect_language("readme.md") is None


class TestStructuralScanner:
    @pytest.fixture
    def scanner(self):
        return StructuralScanner()

    @pytest.fixture
    def py_file(self, tmp_path):
        p = tmp_path / "sample.py"
        p.write_text(
            "class Order:\n"
            "    def create(self):\n"
            "        pass\n"
            "\n"
            "async def fetch_orders():\n"
            "    return []\n"
        )
        return str(p)

    @pytest.mark.asyncio
    async def test_extract_python_symbols(self, scanner, py_file):
        result = await scanner.extract_symbols(py_file)
        assert isinstance(result, FileScanResult)
        assert result.language == "python"
        names = [s.name for s in result.symbols]
        assert "Order" in names
        assert "create" in names
        assert "fetch_orders" in names

    @pytest.mark.asyncio
    async def test_extract_python_class_lines(self, scanner, py_file):
        result = await scanner.extract_symbols(py_file)
        order = next(s for s in result.symbols if s.name == "Order")
        assert order.symbol_type == "class"
        assert order.line_start == 1
        assert order.line_end == 3

    @pytest.mark.asyncio
    async def test_extract_async_function(self, scanner, py_file):
        result = await scanner.extract_symbols(py_file)
        fn = next(s for s in result.symbols if s.name == "fetch_orders")
        assert fn.symbol_type == "async_function"

    @pytest.mark.asyncio
    async def test_scan_nonexistent_file(self, scanner):
        result = await scanner.extract_symbols("/nonexistent/file.py")
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_scan_non_python_no_sg(self, scanner, tmp_path):
        """Non-Python file without sg CLI should return keyword fallback."""
        p = tmp_path / "order_service.go"
        p.write_text('package main\nfunc main() {}\n')
        result = await scanner.extract_symbols(str(p))
        assert result.language == "go"
        # Without sg, falls back to keywords (not structural symbols)
        assert isinstance(result.symbols, list)

    @pytest.mark.asyncio
    async def test_scan_patterns_no_sg(self, scanner, tmp_path):
        """Pattern matching without sg CLI returns empty matches."""
        p = tmp_path / "test.py"
        p.write_text("def foo(): pass\n")
        result = await scanner.scan_patterns(str(p), patterns=["console.log($MSG)"])
        assert result.pattern_matches == []

    @pytest.mark.asyncio
    async def test_scan_files_batch(self, scanner, tmp_path):
        f1 = tmp_path / "a.py"
        f1.write_text("def func_a(): pass\n")
        f2 = tmp_path / "b.py"
        f2.write_text("class MyClass:\n    pass\n")
        results = await scanner.scan_files([str(f1), str(f2)])
        assert len(results) == 2
        assert all(r.language == "python" for r in results)

    @pytest.mark.asyncio
    async def test_scan_files_missing_file(self, scanner, tmp_path):
        results = await scanner.scan_files([str(tmp_path / "missing.py")])
        assert len(results) == 1
        assert results[0].error == "File not found"


# ── API endpoint tests ───────────────────────────────────────────────────


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestStructuralScanAPI:
    def test_scan_python_file(self, client, tmp_path):
        p = tmp_path / "order.py"
        p.write_text("def create_order():\n    pass\n")
        resp = client.post("/api/structural-scan", json={
            "file_paths": [str(p)],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        result = data["results"][0]
        assert result["language"] == "python"
        assert any(s["name"] == "create_order" for s in result["symbols"])

    def test_scan_with_patterns(self, client, tmp_path):
        p = tmp_path / "app.py"
        p.write_text("def foo(): pass\n")
        resp = client.post("/api/structural-scan", json={
            "file_paths": [str(p)],
            "patterns": ["console.log($MSG)"],
        })
        assert resp.status_code == 200
        # Without sg, pattern_matches is empty
        data = resp.json()
        assert data["total"] == 1

    def test_scan_empty_paths(self, client):
        resp = client.post("/api/structural-scan", json={
            "file_paths": [],
        })
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_scan_nonexistent_file(self, client):
        resp = client.post("/api/structural-scan", json={
            "file_paths": ["/nonexistent/file.py"],
        })
        assert resp.status_code == 200
        assert resp.json()["results"][0]["error"] is not None


class TestMCPTools:
    """Test MCP tool logic via direct function calls (not through MCP protocol)."""

    def test_scan_code_patterns_tool(self, tmp_path):
        """Test scan_code_patterns MCP tool directly."""
        # Create a minimal service setup for testing
        import asyncio

        from ai_nexus.db.sqlite import Database
        from ai_nexus.mcp.server import init_services
        from ai_nexus.proxy.mem0_proxy import Mem0Proxy
        from ai_nexus.repos.entity_repo import EntityRepo
        from ai_nexus.repos.relation_repo import RelationRepo
        from ai_nexus.repos.rule_repo import RuleRepo
        from ai_nexus.services.graph_service import GraphService
        from ai_nexus.services.query_service import QueryService

        async def _test():
            db = Database(":memory:")
            await db.connect()
            await db.run_migrations()
            entity_repo = EntityRepo(db)
            relation_repo = RelationRepo(db)
            rule_repo = RuleRepo(db)
            graph_service = GraphService(entity_repo, relation_repo, rule_repo)
            mem0_proxy = Mem0Proxy(base_url="http://localhost:8080")
            query_service = QueryService(graph_service, mem0_proxy)
            init_services(graph_service, query_service)

            # Import tool after init
            from ai_nexus.mcp import server
            result_str = await server.scan_code_patterns(
                file_paths=[str(tmp_path / "missing.py")],
            )
            result = json.loads(result_str)
            assert "results" in result
            await db.disconnect()

        asyncio.get_event_loop().run_until_complete(_test())

    def test_create_code_reference_tool_no_repo(self):
        """Test create_code_reference without repo init returns error."""
        import asyncio

        from ai_nexus.mcp import server

        # Reset state
        server._code_ref_repo = None

        async def _test():
            result_str = await server.create_code_reference(
                rule_id=1,
                file_path="test.py",
                commit_sha="abc123",
            )
            result = json.loads(result_str)
            assert "error" in result

        asyncio.get_event_loop().run_until_complete(_test())
