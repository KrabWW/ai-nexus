"""Phase 0 cleanup tests — TDD approach."""
import subprocess
import sys


def test_mem0ai_not_installed():
    """mem0ai 不应该是项目依赖。"""
    result = subprocess.run(
        [sys.executable, "-c", "import mem0"],
        capture_output=True,
    )
    assert result.returncode != 0, "mem0ai should not be importable as a project dep"


def test_search_module_removed():
    """search/ 模块不应该存在。"""
    result = subprocess.run(
        [sys.executable, "-c", "from ai_nexus.search import provider"],
        capture_output=True,
    )
    assert result.returncode != 0, "ai_nexus.search should be removed"
