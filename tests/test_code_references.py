"""Tests for code anchoring: diff parser, AST analyzer, repo CRUD, API endpoints."""

import pytest
from fastapi.testclient import TestClient

from ai_nexus.main import app
from ai_nexus.services.ast_analyzer import (
    CodeSymbol,
    extract_keywords_from_path,
    extract_symbols,
    find_symbol_at_line,
    keywords_overlap,
)
from ai_nexus.services.diff_parser import extract_snippet, parse_unified_diff

# ── Diff Parser ──────────────────────────────────────────────────────────


class TestParseUnifiedDiff:
    def test_empty_input(self):
        assert parse_unified_diff("") == []
        assert parse_unified_diff("   ") == []

    def test_single_file_single_hunk(self):
        diff = (
            "diff --git a/src/order.py b/src/order.py\n"
            "index abc..def 100644\n"
            "--- a/src/order.py\n"
            "+++ b/src/order.py\n"
            "@@ -10,3 +10,4 @@ def create_order():\n"
            "     pass\n"
            "+    validate_stock()\n"
            "     return order\n"
        )
        results = parse_unified_diff(diff)
        assert len(results) == 1
        assert results[0].file_path == "src/order.py"
        assert len(results[0].hunks) == 1
        h = results[0].hunks[0]
        assert h.line_start == 10
        assert h.line_end == 13  # 10 + 4 - 1
        assert "+    validate_stock()" in h.content

    def test_multiple_files(self):
        diff = (
            "diff --git a/a.py b/a.py\n"
            "@@ -1,3 +1,3 @@\n"
            " old\n"
            "+new\n"
            "diff --git a/b.py b/b.py\n"
            "@@ -5,2 +5,3 @@\n"
            " ctx\n"
            "+added\n"
        )
        results = parse_unified_diff(diff)
        assert len(results) == 2
        assert results[0].file_path == "a.py"
        assert results[1].file_path == "b.py"

    def test_binary_file_skipped(self):
        diff = (
            "diff --git a/image.png b/image.png\n"
            "Binary files a/image.png and b/image.png differ\n"
        )
        results = parse_unified_diff(diff)
        assert results == []

    def test_deleted_file_skipped(self):
        diff = (
            "diff --git a/old.py b/old.py\n"
            "--- a/old.py\n"
            "+++ /dev/null\n"
            "@@ -1,3 +0,0 @@\n"
            "-removed\n"
        )
        results = parse_unified_diff(diff)
        assert results == []

    def test_mode_change_ignored(self):
        diff = (
            "diff --git a/script.sh b/script.sh\n"
            "old mode 100644\n"
            "new mode 100755\n"
        )
        results = parse_unified_diff(diff)
        assert results == []

    def test_hunk_with_no_count(self):
        diff = (
            "diff --git a/f.py b/f.py\n"
            "@@ -5 +5,2 @@\n"
            " ctx\n"
            "+new\n"
        )
        results = parse_unified_diff(diff)
        assert len(results) == 1
        assert results[0].hunks[0].line_start == 5
        assert results[0].hunks[0].line_end == 6  # 5 + 2 - 1


class TestExtractSnippet:
    def test_basic(self):
        content = " context\n+added\n-removed\n more"
        snippet = extract_snippet(content)
        assert "context" in snippet
        assert "added" in snippet
        assert "removed" in snippet

    def test_strips_prefix(self):
        content = "+added line"
        assert extract_snippet(content) == "added line"

    def test_empty(self):
        assert extract_snippet("") == ""

    def test_no_newline_marker(self):
        content = " line1\n\\ No newline at end of file"
        assert "\\ No newline" not in extract_snippet(content)


# ── AST Analyzer ─────────────────────────────────────────────────────────


class TestExtractSymbols:
    def test_simple_function(self):
        src = "def foo():\n    pass\n"
        syms = extract_symbols(src)
        assert len(syms) == 1
        assert syms[0].name == "foo"
        assert syms[0].symbol_type == "function"
        assert syms[0].line_start == 1
        assert syms[0].line_end == 2

    def test_async_function(self):
        src = "async def fetch():\n    await stuff()\n"
        syms = extract_symbols(src)
        assert len(syms) == 1
        assert syms[0].symbol_type == "async_function"

    def test_class(self):
        src = "class Foo:\n    def bar(self):\n        pass\n"
        syms = extract_symbols(src)
        names = [s.name for s in syms]
        assert "Foo" in names
        assert "bar" in names
        class_sym = next(s for s in syms if s.name == "Foo")
        assert class_sym.symbol_type == "class"
        assert class_sym.line_end == 3

    def test_syntax_error_returns_empty(self):
        assert extract_symbols("def (broken") == []

    def test_empty_source(self):
        assert extract_symbols("") == []


class TestFindSymbolAtLine:
    def test_inside_function(self):
        syms = [CodeSymbol("foo", "function", 1, 5)]
        assert find_symbol_at_line(syms, 3) == syms[0]

    def test_outside(self):
        syms = [CodeSymbol("foo", "function", 1, 5)]
        assert find_symbol_at_line(syms, 10) is None

    def test_empty_symbols(self):
        assert find_symbol_at_line([], 1) is None


class TestExtractKeywordsFromPath:
    def test_basic(self):
        kws = extract_keywords_from_path("src/services/order_service.py")
        assert "order" in kws
        assert "service" in kws
        # stop words filtered
        assert "src" not in kws
        assert "py" not in kws

    def test_empty(self):
        assert extract_keywords_from_path("") == []

    def test_camel_case_path(self):
        kws = extract_keywords_from_path("OrderController.java")
        # Splits on _-./ only, not CamelCase — whole token becomes lowercase
        assert "ordercontroller" in kws
        assert "java" not in kws  # stop word


class TestKeywordsOverlap:
    def test_match(self):
        class FakeRule:
            name = "订单规则"
            description = "订单创建校验"
            domain = "交易"
        assert keywords_overlap(["订单"], FakeRule()) is True

    def test_no_match(self):
        class FakeRule:
            name = "支付规则"
            description = "支付校验"
            domain = "支付"
        assert keywords_overlap(["库存"], FakeRule()) is False

    def test_empty_keywords(self):
        class FakeRule:
            name = "test"
            description = "desc"
            domain = "d"
        assert keywords_overlap([], FakeRule()) is False

    def test_or_logic(self):
        class FakeRule:
            name = "订单"
            description = "desc"
            domain = "d"
        assert keywords_overlap(["支付", "订单"], FakeRule()) is True


# ── API Tests ────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _create_rule(client, name="测试规则", severity="warning"):
    resp = client.post("/api/rules", json={
        "name": name,
        "description": f"{name}的描述",
        "domain": "交易",
        "severity": severity,
        "status": "approved",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


class TestCodeReferenceCRUD:
    def test_create_and_get(self, client):
        rule_id = _create_rule(client)
        resp = client.post("/api/code-references", json={
            "rule_id": rule_id,
            "file_path": "src/order.py",
            "line_start": 10,
            "line_end": 15,
            "snippet": "def create_order():\n    pass",
            "commit_sha": "abc123def456",
            "branch": "main",
            "reference_type": "violation",
            "source": "pre_commit",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["file_path"] == "src/order.py"
        assert data["rule_id"] == rule_id
        ref_id = data["id"]

        # GET by id
        get_resp = client.get(f"/api/code-references/{ref_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["commit_sha"] == "abc123def456"

    def test_list_by_rule(self, client):
        rule_id = _create_rule(client, name="列表规则")
        client.post("/api/code-references", json={
            "rule_id": rule_id,
            "file_path": "a.py",
            "commit_sha": "sha1",
        })
        client.post("/api/code-references", json={
            "rule_id": rule_id,
            "file_path": "b.py",
            "commit_sha": "sha2",
        })
        resp = client.get("/api/code-references", params={"rule_id": rule_id})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    def test_list_by_file(self, client):
        rule_id = _create_rule(client, name="文件规则")
        client.post("/api/code-references", json={
            "rule_id": rule_id,
            "file_path": "path/to/unique_file_xyz.py",
            "commit_sha": "sha3",
        })
        resp = client.get(
            "/api/code-references",
            params={"file_path": "path/to/unique_file_xyz.py"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1
        assert all(i["file_path"] == "path/to/unique_file_xyz.py" for i in resp.json()["items"])

    def test_delete(self, client):
        rule_id = _create_rule(client, name="删除规则")
        resp = client.post("/api/code-references", json={
            "rule_id": rule_id,
            "file_path": "del.py",
            "commit_sha": "sha_del",
        })
        ref_id = resp.json()["id"]
        del_resp = client.delete(f"/api/code-references/{ref_id}")
        assert del_resp.status_code == 204
        # verify gone
        assert client.get(f"/api/code-references/{ref_id}").status_code == 404

    def test_get_not_found(self, client):
        assert client.get("/api/code-references/99999").status_code == 404

    def test_delete_not_found(self, client):
        assert client.delete("/api/code-references/99999").status_code == 404


class TestPreCommitWithCodeRefs:
    def test_pre_commit_creates_code_refs(self, client):
        """Pre-commit with diff + commit_sha should create code references."""
        # Use English in rule name so keyword overlap matches file path
        _create_rule(client, name="order creation rule", severity="critical")

        diff = (
            "diff --git a/src/order/create.py b/src/order/create.py\n"
            "@@ -10,3 +10,4 @@ def create_order():\n"
            "     pass\n"
            "+    validate_stock()\n"
            "     return order\n"
        )
        resp = client.post("/api/hooks/pre-commit", json={
            "change_description": "修改order创建逻辑",
            "affected_entities": ["order"],
            "diff_content": diff,
            "commit_sha": "feat123abc",
            "branch": "main",
            "repo_url": "https://github.com/test/repo",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] is False  # critical rule matched → errors
        assert data["code_references_created"] >= 1

    def test_pre_commit_no_diff_no_refs(self, client):
        """Pre-commit without diff should not create code references."""
        _create_rule(client, name="无diff规则", severity="info")
        resp = client.post("/api/hooks/pre-commit", json={
            "change_description": "普通修改",
        })
        assert resp.status_code == 200
        assert resp.json()["code_references_created"] == 0


class TestConsoleRuleDetail:
    def test_rule_detail_page(self, client):
        rule_id = _create_rule(client, name="详情页规则")
        # Add a code reference
        client.post("/api/code-references", json={
            "rule_id": rule_id,
            "file_path": "detail_test.py",
            "line_start": 5,
            "line_end": 10,
            "snippet": "def test():\n    pass",
            "commit_sha": "detail_sha",
            "branch": "main",
            "reference_type": "violation",
            "source": "pre_commit",
        })
        resp = client.get(f"/console/rules/{rule_id}/detail")
        assert resp.status_code == 200
        html = resp.text
        assert "详情页规则" in html
        assert "detail_test.py" in html
        assert "detail_sha" in html

    def test_rule_detail_not_found(self, client):
        resp = client.get("/console/rules/99999/detail")
        assert resp.status_code == 404
