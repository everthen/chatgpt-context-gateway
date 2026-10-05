import pytest

mcp = pytest.importorskip("mcp")

from context_gateway.mcp_server import build_mcp


def test_mcp_read_only_tool_registry(tmp_path):
    server = build_mcp(tmp_path / "mcp.sqlite3")
    names = [tool.name for tool in server._tool_manager.list_tools()]
    assert names == [
        "context_request",
        "context_search",
        "context_get_conversation",
        "context_get_snapshot",
        "context_project_context",
        "context_timeline",
        "context_continuity",
        "context_compare",
    ]
