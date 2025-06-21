#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=0.1.0"]
# ///
"""
`mcp_fd_server.py` – An MCP server that exposes lightning‑fast file search and
fuzzy filtering powered by **fd** and **fzf**.

Two tools are available inside Claude Code once you register the server:

* **`search_files`** – run `fd` and return every match as a list.
* **`filter_files`** – pipe the `fd` output through *fzf*'s non‑interactive
  `--filter` mode and return the filtered subset (or the single best match if
  `--first` is requested).

Why use `--filter` instead of interactive TUI? Claude Code talks to the server
via stdio—not a TTY—so interactive mode would hang. The `--filter` flag lets us
keep all of fzf’s fuzzy‑matching goodness in a headless context.

Example prompts
---------------
```
/ search_files pattern:"\\.rs$" path:"src" flags:"--hidden"
/ filter_files pattern:"" path:"." filter:"main" first:true
```

The second call prints the **first** file whose fuzzy score matches "main" best
according to fzf.

Shebang & dependencies
----------------------
The script is completely self‑contained thanks to the `uv --script` shebang and
inline dependency block. Make it executable (`chmod +x ...`) and either:

```bash
./mcp_fd_server.py               # CLI mode (see --help)
claude mcp add fd-fzf ./mcp_fd_server.py   # MCP mode for Claude Code
```

Python depends only on `mcp>=0.1.0`; the external binaries **fd**, **fzf**, and
optionally **bat** (for preview) must be on `$PATH`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from mcp import start_server, tool

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
# MCP tools
# ---------------------------------------------------------------------------


@tool(
    name="search_files",
    description=(
        "Find files using *fd*.\n\n"
        "Parameters:\n"
        "  pattern (str): Regex or glob to match. Required.\n"
        "  path (str, optional): Directory to search. Defaults to current dir.\n"
        "  flags (str, optional): Extra flags forwarded to fd.\n\n"
        "Returns: { matches: string[] } or { error: string }"
    ),
)
def search_files(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return every file/directory that matches *pattern* according to fd."""
    pattern = params.get("pattern")
    if not pattern:
        return {"error": "'pattern' argument is required"}

    path = params.get("path", ".")
    flags = params.get("flags", "")

    fd_bin = _require(FD_EXECUTABLE, "fd")
    cmd: List[str] = [fd_bin, *shlex.split(flags), pattern, path]

    logger.debug("Running fd: %s", " ".join(shlex.quote(c) for c in cmd))

    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
        return {"matches": [p for p in out.splitlines() if p]}
    except subprocess.CalledProcessError as exc:
        return {"error": exc.output.strip() or str(exc)}


@tool(
    name="filter_files",
    description=(
        "Run fd, then fuzzy‑filter with fzf --filter.\n\n"
        "Parameters:\n"
        "  pattern (str): Pattern for fd (can be empty to list all).\n"
        "  filter (str): String passed to fzf --filter. Required.\n"
        "  path (str, optional): Directory to search. Defaults to current dir.\n"
        "  first (bool, optional): Return only the best match. Default false.\n"
        "  fd_flags (str, optional): Extra flags to fd.\n"
        "  fzf_flags (str, optional): Extra flags to fzf (e.g. '--no-sort').\n\n"
        "Returns: { matches: string[] } or { error: string }"
    ),
)
def filter_files(params: Dict[str, Any]) -> Dict[str, Any]:
    """Combine fd + fzf in non‑interactive filter mode."""
    filter_str = params.get("filter")
    if not filter_str:
        return {"error": "'filter' argument is required"}

    pattern = params.get("pattern", "")
    path = params.get("path", ".")
    first = bool(params.get("first", False))
    fd_flags = params.get("fd_flags", "")
    fzf_flags = params.get("fzf_flags", "")

    fd_bin = _require(FD_EXECUTABLE, "fd")
    fzf_bin = _require(FZF_EXECUTABLE, "fzf")

    fd_cmd = [fd_bin, *shlex.split(fd_flags), pattern, path]
    fzf_cmd = [fzf_bin, "--filter", filter_str, *shlex.split(fzf_flags)]

    if first:
        fzf_cmd.append("--nth=1")  # first match only

    logger.debug("Pipeline: %s | %s", " ".join(fd_cmd), " ".join(fzf_cmd))

    try:
        fd_proc = subprocess.Popen(fd_cmd, stdout=subprocess.PIPE)
        out = subprocess.check_output(fzf_cmd, stdin=fd_proc.stdout, text=True)
        fd_proc.stdout.close()  # allow fd to receive SIGPIPE if fzf exits early
        fd_proc.wait()

        matches = [p for p in out.splitlines() if p]
        if first and matches:
            matches = matches[:1]
        return {"matches": matches}
    except subprocess.CalledProcessError as exc:
        return {"error": exc.output.strip() or str(exc)}


# ---------------------------------------------------------------------------
# CLI helper (optional) ------------------------------------------------------
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="fd + fzf powers, CLI mode")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # search_files sub‑command
    p_search = sub.add_parser("search", help="fd search")
    p_search.add_argument("pattern")
    p_search.add_argument("path", nargs="?", default=".")
    p_search.add_argument("--flags", default="")

    # filter_files sub‑command
    p_filter = sub.add_parser("filter", help="fd + fzf filter")
    p_filter.add_argument("filter")
    p_filter.add_argument("pattern", nargs="?", default="")
    p_filter.add_argument("path", nargs="?", default=".")
    p_filter.add_argument("--first", action="store_true")
    p_filter.add_argument("--fd-flags", default="")
    p_filter.add_argument("--fzf-flags", default="")

    ns = parser.parse_args()

    if ns.cmd == "search":
        res = search_files(vars(ns))
    else:
        res = filter_files(vars(ns))

    print(json.dumps(res, indent=2))


# ---------------------------------------------------------------------------
# Entry‑point ---------------------------------------------------------------
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli()  # invoked with args → behave like CLI helper
    else:
        logger.info("Starting MCP server exposing search_files & filter_files tools")
        # Fail early if required binaries are missing.
        _require(FD_EXECUTABLE, "fd")
        _require(FZF_EXECUTABLE, "fzf")
        start_server(globals())
