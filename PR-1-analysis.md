# PR #1 Review — feat: add limit parameters

PR: https://github.com/dashed/mcp-personal/pull/1

Status: merged (CLEAN/mergeable)

Author: @Acren (Sam Bonifacio)

Branch: feat/add-limit-params → master

Changed files: 3 (README.md, mcp_fd_server.py, tests/test_fd_server.py)

Additions/Deletions: +18 / −5

Date reviewed: 2025-08-08

## Summary

Adds an optional `limit` parameter to both `search_files` and `filter_files` so callers can cap returned results. Exposes `--limit` via the CLI for both subcommands. Keeps backward compatibility (existing positional and keyword calls continue to work). Updates README and one test to account for the new parameter in function signatures.

## Changes by File

- README.md
  - Documents new `limit` parameter for `search_files` and `filter_files`.

- mcp_fd_server.py
  - `search_files(pattern, path='.', limit=0, flags='')`: slices matches when `limit > 0`.
  - `filter_files(filter, pattern='', path='.', first=False, limit=0, fd_flags='', fzf_flags='', multiline=False)`: if `first` is true, returns a single result; otherwise applies `limit` when `limit > 0`.
  - CLI:
    - `search` subcommand: adds `--limit` and passes as positional arg to `search_files`.
    - `filter` subcommand: adds `--limit` and passes along with other args to `filter_files`.
  - Tool descriptions updated to include `limit`.

- tests/test_fd_server.py
  - `test_multiline_cli_support`: updates positional argument index in assertion to reflect insertion of `limit` in the `filter_files` signature.

## Correctness & Compatibility

- Backward compatibility preserved:
  - Existing calls such as `search_files('*.py', '.')` map to `pattern`, `path` unchanged; `limit`/`flags` default.
  - Keyword-based usage in tests and MCP calls remains valid.
- Precedence is explicit in code: in `filter_files`, `first` overrides `limit`.
- Tool descriptions and README updated accordingly.

## CLI Behavior

- `search`: `--limit` is optional; when provided, the CLI calls `search_files(pattern, path, limit, flags)`.
- `filter`: `--limit` is optional; when provided, applies after `first` precedence.

## Documentation

- README documents `limit` for both tools. Consider adding a brief note clarifying that `first` takes precedence over `limit` when both are set.

## Tests

- One test updated to reflect signature change. Suggested follow-ups:
  - Add tests covering `search_files(..., limit=1)` result trimming.
  - Add tests for `filter_files(..., limit=N)` and CLI `--limit` (standard and multiline) to lock in behavior.

## Performance & Design Notes

- `search_files`: limiting is applied after collecting all results from `fd`. This is correct but could be more efficient when many files are present. Consider passing a native limit to `fd` (e.g., `-n/--max-results`) when `limit > 0`, in addition to the current post-slice for safety.
- `filter_files`: limiting after `fzf` preserves fzf’s scoring/sorting semantics; this is appropriate. For multiline mode, trimming after fzf is also correct.
- API shape: using `limit=0` to mean “no limit” is acceptable; an alternative would be `limit: int | None = None` for explicitness, but not required.

## Risk Assessment

- Low risk. Defaults preserve existing behavior. CLI flags are additive. Only one test needed adjustment due to argument ordering.

## MCP Context Check

- Searched local repo and `git-repos/` for related MCP usage; the change is self-contained to `mcp_fd_server.py` and does not impact other MCP components in the `git-repos/` references.

## Verdict

- Safe to merge (already merged). Provides useful control over result counts. Recommend minor follow-ups:
  - Use fd’s native max-results flag when `limit > 0` in `search_files` for efficiency.
  - Add tests for `limit` coverage and a README note on `first` vs `limit` precedence.

## Follow-ups Implemented

- Performance: `search_files` now adds `--max-results <limit>` to the `fd` command when `limit > 0`, and still safety-slices results.
- Documentation: Added note clarifying that `first` takes precedence over `limit` in `filter_files`.
- Tests: Added targeted tests for limit behavior:
  - `tests/test_fd_server.py::test_search_files_limit_uses_fd_max_results_and_trims`
  - `tests/test_cli.py::test_cli_search_limit_mocked`
  - `tests/test_cli.py::test_cli_filter_limit_mocked`
  (No dedicated Makefile target; use `make ci-local` or `make test`.)

## Current Status

- Flag correction: Replaced provisional `-n` with `--max-results` after checking `git-repos/fd` docs and man page.
- Verification: Confirmed `fd --max-results` behavior locally (e.g., `fd --max-results 2 -e py .` returns two results).
- CI run: `make ci-local` passes formatting check, lint, type check, and full test suite (202 tests) on this branch.
- Makefile: `test-limit` removed as requested; use `make ci-local` or `make test`.
- Next steps: None required. Optionally scan for other fd invocations to apply the same optimization (none found in this repo).

## Optional Nice-to-Haves

- Tool docstring: Add an explicit line in the `filter_files` tool description that “when both `first` and `limit` are set, `first` overrides `limit`”.
- Extra tests:
  - Function-level: Assert `filter_files(..., first=True, limit=N)` returns exactly one item and ignores `limit`.
  - CLI-level: Assert `./mcp_fd_server.py filter ... --first --limit N` returns one item and ignores `--limit`.
  - Multiline mode: Add a test that exercises `filter_files(..., multiline=True, limit=N)` and verifies trimming to `N` when `first` is not set.
