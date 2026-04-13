"""Tests for the Sequential Thinking MCP server.

These exercise both the core ``SequentialThinkingServer`` class and the
pydantic-driven argument schema of the registered ``sequentialthinking``
tool, including the JSON-string coercion behavior described in
https://github.com/modelcontextprotocol/servers/issues/3856.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

import mcp_sequential_thinking
from mcp_sequential_thinking import (
    SequentialThinkingServer,
    _process_thought_sync,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> SequentialThinkingServer:
    """A fresh server with thought logging suppressed."""
    monkeypatch.setenv("DISABLE_THOUGHT_LOGGING", "true")
    return SequentialThinkingServer()


@pytest.fixture
def logging_server(monkeypatch: pytest.MonkeyPatch) -> SequentialThinkingServer:
    """A fresh server with thought logging *enabled*."""
    monkeypatch.delenv("DISABLE_THOUGHT_LOGGING", raising=False)
    return SequentialThinkingServer()


# ---------------------------------------------------------------------------
# Valid input tests
# ---------------------------------------------------------------------------


def test_valid_basic_thought(server: SequentialThinkingServer) -> None:
    result = server.process_thought(
        {
            "thought": "This is my first thought",
            "thoughtNumber": 1,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
        }
    )

    assert result["thoughtNumber"] == 1
    assert result["totalThoughts"] == 3
    assert result["nextThoughtNeeded"] is True
    assert result["thoughtHistoryLength"] == 1
    assert result["branches"] == []


def test_thought_with_optional_fields(server: SequentialThinkingServer) -> None:
    result = server.process_thought(
        {
            "thought": "Revising my earlier idea",
            "thoughtNumber": 2,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
            "isRevision": True,
            "revisesThought": 1,
            "needsMoreThoughts": False,
        }
    )

    assert result["thoughtNumber"] == 2
    assert result["thoughtHistoryLength"] == 1


def test_track_multiple_thoughts(server: SequentialThinkingServer) -> None:
    server.process_thought(
        {
            "thought": "First thought",
            "thoughtNumber": 1,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
        }
    )
    server.process_thought(
        {
            "thought": "Second thought",
            "thoughtNumber": 2,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
        }
    )
    result = server.process_thought(
        {
            "thought": "Final thought",
            "thoughtNumber": 3,
            "totalThoughts": 3,
            "nextThoughtNeeded": False,
        }
    )

    assert result["thoughtHistoryLength"] == 3
    assert result["nextThoughtNeeded"] is False


def test_auto_adjust_total_thoughts(server: SequentialThinkingServer) -> None:
    result = server.process_thought(
        {
            "thought": "Thought 5",
            "thoughtNumber": 5,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
        }
    )

    assert result["totalThoughts"] == 5
    assert result["thoughtNumber"] == 5


# ---------------------------------------------------------------------------
# Branching tests
# ---------------------------------------------------------------------------


def test_track_two_branches(server: SequentialThinkingServer) -> None:
    server.process_thought(
        {
            "thought": "Main thought",
            "thoughtNumber": 1,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
        }
    )
    server.process_thought(
        {
            "thought": "Branch A thought",
            "thoughtNumber": 2,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
            "branchFromThought": 1,
            "branchId": "branch-a",
        }
    )
    result = server.process_thought(
        {
            "thought": "Branch B thought",
            "thoughtNumber": 2,
            "totalThoughts": 3,
            "nextThoughtNeeded": False,
            "branchFromThought": 1,
            "branchId": "branch-b",
        }
    )

    assert "branch-a" in result["branches"]
    assert "branch-b" in result["branches"]
    assert len(result["branches"]) == 2
    assert result["thoughtHistoryLength"] == 3


def test_multiple_thoughts_same_branch(server: SequentialThinkingServer) -> None:
    server.process_thought(
        {
            "thought": "Branch thought 1",
            "thoughtNumber": 1,
            "totalThoughts": 2,
            "nextThoughtNeeded": True,
            "branchFromThought": 1,
            "branchId": "branch-a",
        }
    )
    result = server.process_thought(
        {
            "thought": "Branch thought 2",
            "thoughtNumber": 2,
            "totalThoughts": 2,
            "nextThoughtNeeded": False,
            "branchFromThought": 1,
            "branchId": "branch-a",
        }
    )

    assert result["branches"] == ["branch-a"]
    assert len(server.branches["branch-a"]) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_very_long_thought_string(server: SequentialThinkingServer) -> None:
    result = server.process_thought(
        {
            "thought": "a" * 10000,
            "thoughtNumber": 1,
            "totalThoughts": 1,
            "nextThoughtNeeded": False,
        }
    )

    assert result["thoughtNumber"] == 1
    assert result["thoughtHistoryLength"] == 1


def test_single_thought(server: SequentialThinkingServer) -> None:
    result = server.process_thought(
        {
            "thought": "Only thought",
            "thoughtNumber": 1,
            "totalThoughts": 1,
            "nextThoughtNeeded": False,
        }
    )

    assert result["thoughtNumber"] == 1
    assert result["totalThoughts"] == 1
    assert result["nextThoughtNeeded"] is False


def test_next_thought_needed_false(server: SequentialThinkingServer) -> None:
    result = server.process_thought(
        {
            "thought": "Final thought",
            "thoughtNumber": 3,
            "totalThoughts": 3,
            "nextThoughtNeeded": False,
        }
    )
    assert result["nextThoughtNeeded"] is False


# ---------------------------------------------------------------------------
# Response format
# ---------------------------------------------------------------------------


def test_response_format(server: SequentialThinkingServer) -> None:
    result = server.process_thought(
        {
            "thought": "Test thought",
            "thoughtNumber": 1,
            "totalThoughts": 1,
            "nextThoughtNeeded": False,
        }
    )

    assert isinstance(result, dict)
    assert set(result.keys()) == {
        "thoughtNumber",
        "totalThoughts",
        "nextThoughtNeeded",
        "branches",
        "thoughtHistoryLength",
    }
    assert isinstance(result["branches"], list)
    assert isinstance(result["thoughtHistoryLength"], int)

    # Must be JSON-serializable
    import json

    json.dumps(result)


def test_process_thought_sync_helper(server: SequentialThinkingServer) -> None:
    result = _process_thought_sync(
        server,
        {
            "thought": "via sync helper",
            "thoughtNumber": 1,
            "totalThoughts": 1,
            "nextThoughtNeeded": False,
        },
    )
    assert result["thoughtHistoryLength"] == 1


# ---------------------------------------------------------------------------
# Logging behavior
# ---------------------------------------------------------------------------


def test_disable_thought_logging_suppresses_output(
    server: SequentialThinkingServer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    server.process_thought(
        {
            "thought": "Quiet thought",
            "thoughtNumber": 1,
            "totalThoughts": 1,
            "nextThoughtNeeded": False,
        }
    )
    captured = capsys.readouterr()
    assert "Quiet thought" not in captured.err
    assert "💭" not in captured.err


def test_logging_emits_regular_thought(
    logging_server: SequentialThinkingServer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging_server.process_thought(
        {
            "thought": "Loud thought",
            "thoughtNumber": 1,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
        }
    )
    captured = capsys.readouterr()
    assert "Loud thought" in captured.err
    assert "💭 Thought 1/3" in captured.err


def test_logging_emits_revision_thought(
    logging_server: SequentialThinkingServer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging_server.process_thought(
        {
            "thought": "Revised idea",
            "thoughtNumber": 2,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
            "isRevision": True,
            "revisesThought": 1,
        }
    )
    captured = capsys.readouterr()
    assert "🔄 Revision 2/3" in captured.err
    assert "revising thought 1" in captured.err


def test_logging_emits_branch_thought(
    logging_server: SequentialThinkingServer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging_server.process_thought(
        {
            "thought": "Branch idea",
            "thoughtNumber": 2,
            "totalThoughts": 3,
            "nextThoughtNeeded": False,
            "branchFromThought": 1,
            "branchId": "branch-a",
        }
    )
    captured = capsys.readouterr()
    assert "🌿 Branch 2/3" in captured.err
    assert "from thought 1" in captured.err
    assert "ID: branch-a" in captured.err


def test_disable_thought_logging_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISABLE_THOUGHT_LOGGING", "TRUE")
    server = SequentialThinkingServer()
    assert server.disable_thought_logging is True

    monkeypatch.setenv("DISABLE_THOUGHT_LOGGING", "True")
    server2 = SequentialThinkingServer()
    assert server2.disable_thought_logging is True

    monkeypatch.setenv("DISABLE_THOUGHT_LOGGING", "false")
    server3 = SequentialThinkingServer()
    assert server3.disable_thought_logging is False


# ---------------------------------------------------------------------------
# String coercion (issue #3856)
# ---------------------------------------------------------------------------
#
# These tests reach into the pydantic argument model that FastMCP synthesizes
# from the @mcp.tool decorated function. Validating raw payloads through that
# model is exactly what FastMCP does when an MCP client invokes the tool, so
# round-tripping JSON-string inputs through it locks in the issue-3856 fix.


def _build_args_model() -> Any:
    """Return the pydantic model FastMCP built for the sequentialthinking tool.

    Reload the module first so we always pick up the current source rather
    than a stale cached registration when the test suite is re-run.
    """
    importlib.reload(mcp_sequential_thinking)
    tool = mcp_sequential_thinking.mcp._tool_manager.get_tool("sequentialthinking")
    assert tool is not None, "sequentialthinking tool was not registered"
    return tool.fn_metadata.arg_model


def test_coercion_string_int_and_bool() -> None:
    model = _build_args_model()
    parsed = model.model_validate(
        {
            "thought": "string-coerced thought",
            "thoughtNumber": "1",
            "totalThoughts": "3",
            "nextThoughtNeeded": "true",
        }
    )
    assert parsed.thoughtNumber == 1
    assert parsed.totalThoughts == 3
    assert parsed.nextThoughtNeeded is True
    assert isinstance(parsed.thoughtNumber, int)
    assert isinstance(parsed.totalThoughts, int)
    assert isinstance(parsed.nextThoughtNeeded, bool)


def test_coercion_string_false() -> None:
    model = _build_args_model()
    parsed = model.model_validate(
        {
            "thought": "done",
            "thoughtNumber": "2",
            "totalThoughts": "2",
            "nextThoughtNeeded": "false",
        }
    )
    assert parsed.nextThoughtNeeded is False


def test_coercion_string_optional_fields() -> None:
    model = _build_args_model()
    parsed = model.model_validate(
        {
            "thought": "revisit",
            "thoughtNumber": "3",
            "totalThoughts": "5",
            "nextThoughtNeeded": "true",
            "isRevision": "true",
            "revisesThought": "1",
            "branchFromThought": "2",
            "branchId": "branch-x",
            "needsMoreThoughts": "false",
        }
    )
    assert parsed.isRevision is True
    assert parsed.revisesThought == 1
    assert parsed.branchFromThought == 2
    assert parsed.branchId == "branch-x"
    assert parsed.needsMoreThoughts is False


def test_coercion_native_types_still_work() -> None:
    model = _build_args_model()
    parsed = model.model_validate(
        {
            "thought": "native types",
            "thoughtNumber": 4,
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
            "isRevision": False,
        }
    )
    assert parsed.thoughtNumber == 4
    assert parsed.totalThoughts == 5
    assert parsed.nextThoughtNeeded is True
    assert parsed.isRevision is False


def test_coercion_case_insensitive_bool_string() -> None:
    model = _build_args_model()
    parsed = model.model_validate(
        {
            "thought": "case",
            "thoughtNumber": "1",
            "totalThoughts": "1",
            "nextThoughtNeeded": "TRUE",
        }
    )
    assert parsed.nextThoughtNeeded is True

    parsed2 = model.model_validate(
        {
            "thought": "case",
            "thoughtNumber": "1",
            "totalThoughts": "1",
            "nextThoughtNeeded": "False",
        }
    )
    assert parsed2.nextThoughtNeeded is False
