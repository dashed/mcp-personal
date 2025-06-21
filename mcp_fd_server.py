#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=0.1.0"]
#
# [project.optional-dependencies]
# dev = ["pytest>=7.0", "pytest-asyncio>=0.21.0"]
# ///
"""
`mcp_fd_server.py` – Minimal but complete **Model Context Protocol** server
(implemented with the official **FastMCP** helper that ships inside the
`mcp` Python SDK) exposing two file‑search tools powered by **fd** and
**fzf**.

Tools exposed to LLMs
--------------------
* **`search_files`** – list files using `fd` (fast `find`).
* **`filter_files`** – pipe the `fd` output through `fzf --filter` for fuzzy,
  *headless* matching (perfect for non‑interactive stdio environments).

Quick start
-----------
```bash
# Make sure binaries are on PATH first
brew install fd fzf bat      # macOS example
# or apt install fd-find fzf bat   # Debian/Ubuntu (symlink fdfind→fd)

chmod +x mcp_fd_server.py    # mark as executable

# 1. Stand‑alone CLI helper
./mcp_fd_server.py search "\\.py$" src --flags "--hidden"  # lists .py files
./mcp_fd_server.py filter main "" . --first                # best fuzzy match

# 2. Run as MCP stdio server (for Claude Code / Inspector)
./mcp_fd_server.py           # blocks, prints MCP init JSON
```

Internals
---------
* Uses **FastMCP** for attribute‑based discovery (`@mcp.tool`). No manual
  server boilerplate needed—just call `mcp.run()`.
* Shebang **uv run --script** + inline `[dependencies]` block means the first
  launch automatically installs the `mcp` SDK into an isolated cache.
* All error cases return structured JSON `{ "error": "..." }` so the LLM can
  react programmatically.
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import shutil
import subprocess
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP  # high‑level helper inside the SDK

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Binary discovery helpers
# ---------------------------------------------------------------------------

FD_EXECUTABLE: str | None = shutil.which("fd") or shutil.which("fdfind")
FZF_EXECUTABLE: str | None = shutil.which("fzf")


class BinaryMissing(RuntimeError):
    """Raised when a required CLI binary is missing from PATH."""


def _require(binary: str | None, name: str) -> str:
    if not binary:
        raise BinaryMissing(
            f"Cannot find the `{name}` binary on PATH. Install it first."
        )
    return binary


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("fd-fzf")

# ---------------------------------------------------------------------------
# Tool: search_files
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Find files using *fd*.\n\n"
        "Args:\n"
        "  pattern (str): Regex or glob to match. Required.\n"
        "  path    (str, optional): Directory to search. Defaults to current dir.\n"
        "  flags   (str, optional): Extra flags forwarded to fd.\n\n"
        "Returns: { matches: string[] } or { error: string }"
    )
)
def search_files(
    pattern: str,
    path: str = ".",
    flags: str = "",
) -> dict[str, Any]:
    """Return every file or directory matching *pattern* according to fd."""
    if not pattern:
        return {"error": "'pattern' argument is required"}

    fd_bin = _require(FD_EXECUTABLE, "fd")
    cmd: list[str] = [fd_bin, *shlex.split(flags), pattern, path]

    logger.debug("Running fd: %s", " ".join(shlex.quote(c) for c in cmd))

    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
        return {"matches": [p for p in out.splitlines() if p]}
    except subprocess.CalledProcessError as exc:
        return {"error": exc.output.strip() or str(exc)}


# ---------------------------------------------------------------------------
# Tool: filter_files
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Run fd, then fuzzy‑filter with fzf --filter.\n\n"
        "Args:\n"
        "  filter (str): fzf query string with advanced syntax support. Required.\n"
        "  pattern (str, optional): Pattern for fd (empty = list all).\n"
        "  path    (str, optional): Directory to search. Defaults to current dir.\n"
        "  first   (bool, optional): Return only the best match. Default false.\n"
        "  fd_flags  (str, optional): Extra flags for fd.\n"
        "  fzf_flags (str, optional): Extra flags for fzf.\n"
        "  multiline (bool, optional): Enable multiline support for file content. Default false.\n\n"
        "fzf Query Syntax:\n"
        "  Basic: 'term1 term2' (AND logic), 'term1 | term2' (OR logic)\n"
        "  Exact: ''exact'' (exact match), 'term (partial exact)\n"
        "  Position: '^start' (prefix), 'end$' (suffix), '^exact$' (equal)\n"
        "  Negation: '!exclude' (NOT), '!^prefix' (NOT prefix), '!end$' (NOT suffix)\n"
        "  Examples: 'config .json$', '^src py$ | js$ | go$', ''main.py'' !test'\n\n"
        "Multiline Mode:\n"
        "  When enabled, processes file contents as multiline records using null delimiters.\n"
        "  Useful for filtering entire file contents, code blocks, or structured data.\n"
        "  Automatically adds --read0 --print0 flags to fzf for safe multiline handling.\n\n"
        "Returns: { matches: string[] } or { error: string }"
    )
)
def filter_files(
    filter: str,
    pattern: str = "",
    path: str = ".",
    first: bool = False,
    fd_flags: str = "",
    fzf_flags: str = "",
    multiline: bool = False,
) -> dict[str, Any]:
    """Combine fd + fzf in headless filter mode with optional multiline support."""
    if not filter:
        return {"error": "'filter' argument is required"}

    fd_bin = _require(FD_EXECUTABLE, "fd")
    fzf_bin = _require(FZF_EXECUTABLE, "fzf")

    if multiline:
        # For multiline mode, find files first, then read contents with null separators
        fd_cmd: list[str] = [fd_bin, *shlex.split(fd_flags), pattern, path]
        
        try:
            # Get file list from fd
            fd_result = subprocess.check_output(fd_cmd, text=True)
            file_paths = [p for p in fd_result.splitlines() if p]
            
            # Read file contents with null separators
            multiline_input = b""
            for file_path in file_paths:
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        # Add filename prefix and null separator
                        record = f"{file_path}:\n".encode('utf-8') + content + b'\0'
                        multiline_input += record
                except (IOError, OSError):
                    continue  # Skip files that can't be read
            
            if not multiline_input:
                return {"matches": []}
            
            # Use fzf with multiline support
            fzf_cmd: list[str] = [fzf_bin, "--filter", filter, "--read0", "--print0"]
            fzf_cmd.extend(shlex.split(fzf_flags))
            
            fzf_proc = subprocess.Popen(
                fzf_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=False
            )
            out_bytes, _ = fzf_proc.communicate(multiline_input)
            
            # Parse null-separated output
            matches = []
            if out_bytes:
                for chunk in out_bytes.split(b'\0'):
                    if chunk:
                        try:
                            matches.append(chunk.decode('utf-8'))
                        except UnicodeDecodeError:
                            matches.append(chunk.decode('utf-8', errors='replace'))
            
        except subprocess.CalledProcessError as exc:
            return {"error": str(exc)}
    else:
        # Standard mode - file paths only
        fd_cmd: list[str] = [fd_bin, *shlex.split(fd_flags), pattern, path]
        fzf_cmd: list[str] = [fzf_bin, "--filter", filter, *shlex.split(fzf_flags)]

        logger.debug("Pipeline: %s | %s", " ".join(fd_cmd), " ".join(fzf_cmd))

        try:
            fd_proc = subprocess.Popen(fd_cmd, stdout=subprocess.PIPE)
            out = subprocess.check_output(fzf_cmd, stdin=fd_proc.stdout, text=True)
            fd_proc.stdout.close()
            fd_proc.wait()
            matches = [p for p in out.splitlines() if p]
        except subprocess.CalledProcessError as exc:
            return {"error": str(exc)}

    if first and matches:
        matches = matches[:1]
    return {"matches": matches}


# ---------------------------------------------------------------------------
# CLI helper (optional) ------------------------------------------------------
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="fd + fzf powers, CLI mode",
        epilog="fzf query examples: 'config .json$', '^src py$ | js$', ''main.py'' !test'"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # search_files sub‑command
    p_search = sub.add_parser("search", help="fd search")
    p_search.add_argument("pattern")
    p_search.add_argument("path", nargs="?", default=".")
    p_search.add_argument("--flags", default="")

    # filter_files sub‑command
    p_filter = sub.add_parser("filter", help="fd + fzf filter")
    p_filter.add_argument("filter", help="fzf query (use quotes: 'config .json$ !test')")
    p_filter.add_argument("pattern", nargs="?", default="")
    p_filter.add_argument("path", nargs="?", default=".")
    p_filter.add_argument("--first", action="store_true")
    p_filter.add_argument("--fd-flags", default="")
    p_filter.add_argument("--fzf-flags", default="")
    p_filter.add_argument("--multiline", action="store_true", help="Enable multiline content search")

    ns = parser.parse_args()

    if ns.cmd == "search":
        res = search_files(ns.pattern, ns.path, ns.flags)
    else:
        res = filter_files(
            ns.filter, ns.pattern, ns.path, ns.first, ns.fd_flags, ns.fzf_flags, ns.multiline
        )

    print(json.dumps(res, indent=2))


# ---------------------------------------------------------------------------
# Entry‑point ---------------------------------------------------------------
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli()
    else:
        # Ensure required binaries before exposing tools to LLMs
        _require(FD_EXECUTABLE, "fd")
        _require(FZF_EXECUTABLE, "fzf")
        mcp.run()  # defaults to stdio transport
