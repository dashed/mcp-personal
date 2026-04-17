# Sequential Thinking — Python Port Fidelity Audit

**Date:** 2026-04-16
**Port under audit:** [`mcp_sequential_thinking.py`](./mcp_sequential_thinking.py)
**Reference (TypeScript) source:** `/Users/me/aaa/github/mcp-anthropic-servers/src/sequentialthinking/` — `index.ts`, `lib.ts`, `__tests__/lib.test.ts`
**MCP Python SDK version pinned in `uv.lock`:** `mcp==1.9.4` (checked out under `git-repos/python-sdk/`)

## Verdict

The port is **semantically faithful but wire-format-incomplete**. Core behavior (history, branching, auto-adjust of `totalThoughts`, response keys and values) is byte-equivalent. Fidelity gaps cluster in two places:

1. **Tool registration metadata** that FastMCP 1.9.4 supports but the port does not pass (`title`, `annotations`).
2. **`structuredContent` / `outputSchema`** that the pinned SDK version cannot emit at all.

There is **one** wire-format-breaking finding (missing `structuredContent`/`outputSchema`), **five** behavior-divergences, and several intentional rendering enhancements in the Python port that are explicitly cataloged and covered by Python-only tests.

## Findings summary

| # | Finding | Severity |
|---|---------|----------|
| A | No `structuredContent` emitted; no `outputSchema` in `tools/list` (SDK 1.9.4 has no such fields) | **wire-format-breaking** |
| B | Missing `title="Sequential Thinking"` and `annotations={readOnlyHint, destructiveHint, idempotentHint, openWorldHint}` on `@mcp.tool()` | behavior-divergence |
| C | Numeric coercion rejects `"1.0"`, `"1e2"`, `"0x10"` that zod's `z.coerce.number().int()` accepts | behavior-divergence |
| D | Bool coercion over-shoots zod — pydantic v2 lax mode silently accepts `0`/`1`/`"yes"`/`"no"`/`"on"`/`"off"`/`" True "` | behavior-divergence |
| E | `initialize` handshake: `serverInfo.name` = `"Sequential Thinking"` (vs TS `"sequential-thinking-server"`), `version` = installed `mcp` pkg version (vs TS `"0.2.0"`) | behavior-divergence |
| F | Error-path body differs: TS returns JSON `{"error":"…","status":"failed"}`; Python returns bare string `"Error executing tool sequentialthinking: …"` | behavior-divergence |
| G | Field descriptions for `thoughtNumber`/`totalThoughts` drop the `(numeric value, e.g., 1, 2, 3)` hint (a deliberate [#3856](https://github.com/modelcontextprotocol/servers/issues/3856) mitigation in TS) | cosmetic (weak behavior tint) |
| H | Stderr startup line text and timing differ (`logging.basicConfig` vs `console.error`) | cosmetic |
| I | `formatThought` rendering: word-wrap, width cap, East-Asian-Width emoji handling, ANSI gating | **intentional-enhancement** |

## Methodology

The audit was performed by a three-agent team (`seq-think-audit`, all on Opus 4.6 / 1M context) running in parallel:

- `schema-auditor` — input/output schema, coercion, tool metadata.
- `wire-format-auditor` — tool-return wire format, FastMCP behavior, server metadata, error path.
- `semantics-auditor` — `processThought` runtime semantics and test-coverage parity.

Each teammate used the `fuzzy-search` and `ultrathink` skills. No files were edited. The reports below are reproduced as delivered.

---

## Section 1 — Input-schema & coercion fidelity vs zod

Port file: `mcp_sequential_thinking.py` @ 74–117, 383–441. Reference: `index.ts` @ 25–106. Python SDK pinned at `mcp==1.9.4`; matches `git-repos/python-sdk` v1.9.4-14.

### 1.1 Numeric coercion divergence

- **TS** `z.coerce.number().int().min(1)` → `Number(val)` then int check. Accepts strings `"1.0"`, `"1e2"`, `"1.5e1"`, `"0x10"`, `" 5 "`, and native floats `1.0`. Rejects `"1.5"`, `"abc"`, native `1.5`.
- **Py** `_coerce_int` only accepts native `int` or a string that `int()` parses. Falls through to pydantic for anything else.
- **Divergent inputs Python rejects but TS accepts:** `"1.0"`, `"1e2"` (scientific), `"0x10"` (hex), `"1.5e1"` (scientific → 15). Native `1.0` passes on both sides (pydantic v2 lax int accepts int-valued floats). `" 5 "` → both accept.
- **Bool-as-int:** TS `Number(true)==1` so `thoughtNumber: true` → 1 accepted; Python guards `isinstance(value, bool)` and passes through, pydantic v2 non-strict rejects bool for int.
- **Impact:** a client that serializes `thoughtNumber:"1e2"` or `"1.0"` gets a validation error from Python but not TS.
- **Severity:** behavior-divergence (edge case; real clients mostly emit `"1"`).

### 1.2 Boolean coercion divergence

- **TS** `coercedBoolean`: native bool or exact `"true"/"false"` after `toLowerCase()`. No trim. Everything else → `z.boolean()` → rejects.
- **Py** `_coerce_bool`: strips AND lowercases, so `" True "` is accepted. More importantly, values that fall through (e.g. `0`, `1`, `"yes"`, `"no"`, `"on"`, `"off"`, `"1"`, `"0"`, `"t"`, `"f"`) are handed to pydantic v2 bool, which in **lax mode accepts all of them**.
- **Impact:** Python silently accepts `nextThoughtNeeded: 1` or `"yes"`; TS returns a validation error. Whitespace-wrapped `" true "`: Py accepts, TS rejects.
- **Severity:** behavior-divergence (Python is strictly more permissive; issue #3856 fix over-shoots zod).

### 1.3 Tool metadata fidelity

- **TS `registerTool`** passes `title: "Sequential Thinking"` and `annotations: { readOnlyHint:true, destructiveHint:false, idempotentHint:true, openWorldHint:false }`.
- **Py** `@mcp.tool(description=...)` passes **only** `description`. Title and annotations are **missing**.
- FastMCP 1.9.4 `tool()` decorator (`server.py:333`) supports `title=` and `annotations=ToolAnnotations(...)`; `list_tools` (`server.py:238–250`) propagates both to `MCPTool`. This is a port omission, not an SDK gap.
- **Impact:** clients lose the human-readable title and the read-only/idempotent/non-destructive hints that drive UI affordances and safety gating in some hosts (Inspector, Claude Desktop).
- **Severity:** behavior-divergence.

### 1.4 Output schema

- **TS** declares an explicit `outputSchema` and the handler returns `{ content, structuredContent: parsedContent }` — wire-level `structuredContent` is emitted.
- **Py** returns `dict[str, Any]`. FastMCP 1.9.4 has **no `output_schema` kwarg**, `Tool` model has no output-schema field (`tools/base.py`), `list_tools` never sets `outputSchema`, and `mcp.types` in 1.9.4 has **no `outputSchema` attribute at all**. `_convert_to_content` (`server.py:879–898`) JSON-encodes the dict into a single `TextContent` block; no `structuredContent` is produced.
- **Impact:** MCP clients relying on `structuredContent` (spec 2025-06-18) get only text from Python; clients validating against `outputSchema` see the tool as untyped.
- **Severity:** wire-format-breaking (not catastrophically so — TS also returns text content — but the structured payload is absent and cannot be added without upgrading the SDK).

### 1.5 Description / field-description parity

- Main multi-line description string (`_SEQUENTIAL_THINKING_DESCRIPTION`, lines 327–380) matches `index.ts:29–82` byte-for-byte.
- Per-field `.describe(...)` diffs:
  - `thoughtNumber`: TS `"Current thought number (numeric value, e.g., 1, 2, 3)"` vs Py `"Current thought number (>= 1)"` — **diverges**.
  - `totalThoughts`: TS `"Estimated total thoughts needed (numeric value, e.g., 5, 10)"` vs Py `"Estimated total thoughts needed (>= 1)"` — **diverges**.
  - All other fields (`thought`, `nextThoughtNeeded`, `isRevision`, `revisesThought`, `branchFromThought`, `branchId`, `needsMoreThoughts`) match exactly.
- The TS wording on numeric fields is deliberate (issue #3856 mitigation — hints to string-coercing clients). Dropping it weakens the nudge toward passing numeric literals.
- **Severity:** cosmetic with a slight behavior-divergence tint (field descriptions feed model tool-use prompts).

---

## Section 2 — Tool-return wire format & FastMCP behavior

SDK version under `git-repos/python-sdk/` is pre-`structuredContent` / pre-`outputSchema`. Every answer below is grounded in that tree.

### 2.1 `structuredContent` population

- **TS wire:** `CallToolResult{content:[TextContent], structuredContent:{…}}` (`index.ts:118–121`).
- **Py wire:** `FastMCP.call_tool` returns `Sequence[ContentBlock]` only (`server.py:263–268`); `_convert_to_content` collapses a `dict` return into a single `TextContent` (`server.py:879–898`). Lowlevel handler wraps it: `CallToolResult(content=list(results), isError=False)` (`lowlevel/server.py:395`). `types.CallToolResult` in this SDK has NO `structuredContent` field (`types.py:873–877`).
- **Equivalence:** NOT equivalent — TS has both fields, Python has `content` only.
- **Severity:** MEDIUM. Spec-legal (structuredContent is optional) but any client preferring `structuredContent` / relying on shape validation will downgrade to text parsing.

### 2.2 Pretty-printed JSON body

- **TS:** `JSON.stringify(payload, null, 2)` — 2-space indent.
- **Py:** `pydantic_core.to_json(result, fallback=str, indent=2).decode()` (`server.py:896`) — 2-space indent, dict-insertion-order (matches TS property order: `thoughtNumber`, `totalThoughts`, `nextThoughtNeeded`, `branches`, `thoughtHistoryLength`).
- **Equivalence:** byte-equivalent for this payload.
- **Severity:** NONE.

### 2.3 Synthesized `outputSchema` in `tools/list`

- **TS:** explicit `outputSchema{ thoughtNumber, totalThoughts, nextThoughtNeeded, branches:string[], thoughtHistoryLength }` (`index.ts:100–106`).
- **Py:** `FastMCP.list_tools` constructs `MCPTool(name, title, description, inputSchema, annotations)` — no `outputSchema` arg (`server.py:238–250`). `types.Tool` only declares `inputSchema` (`types.py:835–849`); there is no field for output schema at all in this SDK. A `dict[str, Any]` return annotation is **not** inspected.
- **Equivalence:** NOT equivalent — `outputSchema` absent from Python's `tools/list` entry entirely.
- **Severity:** MEDIUM. Clients that would otherwise validate `structuredContent` against `outputSchema` lose both sides at once (self-consistent, but a capability regression).

### 2.4 `serverInfo` in the `initialize` handshake

- **TS:** `serverInfo = {name:"sequential-thinking-server", version:"0.2.0"}` (`index.ts:18–21`).
- **Py:** `FastMCP("Sequential Thinking")` → `MCPServer(name="Sequential Thinking", ...)` with version unset (`fastmcp/server.py:151–155`). `create_initialization_options` populates `server_version = pkg_version("mcp")` — the installed mcp package version, not `0.2.0` (`lowlevel/server.py:165–167`).
- **Equivalence:** observable on-wire. Both `name` (`"Sequential Thinking"` vs `"sequential-thinking-server"`) and `version` differ.
- **Severity:** MEDIUM. `serverInfo` is free-form so not a protocol violation, but inspectors, logs, and any client keying routing/telemetry on `serverInfo.name` sees a different server.

### 2.5 Stderr startup line

- **TS:** `console.error("Sequential Thinking MCP Server running on stdio")` — literal line, emitted **after** `server.connect(transport)` (`index.ts:125–128`).
- **Py:** `logger.info("Sequential Thinking MCP Server starting on stdio")` (`mcp_sequential_thinking.py:453`), emitted **before** `mcp.run()`. Line 65 runs `logging.basicConfig(level=INFO, format="%(levelname)s | %(message)s")` at import, installing a `StreamHandler` on root; FastMCP's later `configure_logging` call is a no-op because the root logger already has handlers (stdlib contract). Actual bytes: `"INFO | Sequential Thinking MCP Server starting on stdio\n"`.
- **Equivalence:** different text ("starting" vs "running"), `INFO | ` prefix, different timing. Out-of-band (stderr), not on the JSON-RPC wire.
- **Severity:** LOW (cosmetic/diagnostic only).

### 2.6 Error path on unhandled exception

- **TS:** `lib.processThought` try/catches and returns `{isError:true, content:[{type:"text", text: JSON.stringify({error, status:"failed"})}]}` — structured JSON body.
- **Py:** no try/except on the coroutine. `Tool.run` catches everything and re-raises as `ToolError(f"Error executing tool {self.name}: {e}")` (`fastmcp/tools/base.py:89–97`). Bubbles into lowlevel `call_tool` handler which catches `Exception` and returns `CallToolResult(content=[TextContent(type="text", text=str(e))], isError=True)` (`lowlevel/server.py:392–402`). pydantic `ValidationError` takes the same path — surfaces as `isError=true` text, NOT a JSON-RPC `InvalidParams` error.
- **Equivalence:** both produce `isError:true` + a single `TextContent`, so a conformance client sees the same envelope shape. BUT the body differs: TS emits a parseable `{"error":"…","status":"failed"}` JSON blob; Python emits a bare `"Error executing tool sequentialthinking: …"` string. Clients that `JSON.parse(content[0].text)` on errors will break.
- **Severity:** MEDIUM.

### 2.7 Summary (Section 2)

Q1 MED, Q2 NONE, Q3 MED, Q4 MED, Q5 LOW, Q6 MED. The two user-visible fidelity gaps are the missing `structuredContent`/`outputSchema` pair and the `serverInfo` mismatch; both are rooted in the pinned SDK version not exposing those APIs at all, so closing them requires either an SDK upgrade or dropping to the lowlevel `Server` and hand-writing `CallToolResult`/`Tool` dicts.

---

## Section 3 — `processThought` semantics & test parity

### 3.1 State-mutation equivalence

- **TS** (`lib.ts:56-67`): if `thoughtNumber > totalThoughts`, mutates `input.totalThoughts` in place, then `thoughtHistory.push(input)` stores the same (now-mutated) reference; branch push shares that reference.
- **Python** (`mcp_sequential_thinking.py:284-292`): identical — mutates `input_data["totalThoughts"]`, appends the same dict to both `thought_history` and `branches[branch_id]`. Mutation/reference sharing is preserved.
- Response payload keys match exactly: `thoughtNumber`, `totalThoughts`, `nextThoughtNeeded`, `branches` (list of branch IDs), `thoughtHistoryLength`.
- **Severity:** none — semantic parity.
- ⚠ **behavior-divergence (inner envelope):** TS `processThought` returns `{content:[{type:"text",text:JSON.stringify(...)}], isError?}` — a pre-wrapped MCP tool response. Python `process_thought` returns the raw dict and relies on the FastMCP `@mcp.tool` layer to wrap it. End-to-end MCP wire format is equivalent, but the Python core method has no `content`/`isError` envelope and no try/except fallback (FastMCP handles errors). Tests of the inner method therefore legitimately assert different shapes.

### 3.2 Branch-tracking edge cases

- Both skip pushing to `branches` unless **both** `branchFromThought` AND `branchId` are truthy (TS `lib.ts:62`, Py `mcp_sequential_thinking.py:291`). Falsy-0 for `branchFromThought` and empty/undefined `branchId` are both rejected in the same way.
- **Neither** test suite exercises half-specified branches (`branchFromThought` set without `branchId`, or vice versa).
- **Severity:** cosmetic — coverage gap in both. Worth mirroring in Python as a bonus test if desired; no regression.

### 3.3 `formatThought` divergence (intentional, cataloged)

All tagged **intentional-enhancement**:

| Concern | TS (`lib.ts:24-50`) | Python (`mcp_sequential_thinking.py:205-273`) |
|---|---|---|
| Max line width | Unbounded (border sized to `max(header.length, thought.length)`) | `max(20, min(terminal-4, 100))` via `_resolve_max_content_width` |
| Multi-line thoughts | Embeds raw `\n` inside the single `│ … │` line → box breaks | `splitlines()`, each line `textwrap.wrap`-ped, each segment on its own row |
| Emoji width | `header.length` counts surrogate pairs as 2 code units; `chalk.blue(...)` adds ANSI bytes that inflate length further → ragged | `_display_width` via `unicodedata.east_asian_width` (W/F → 2 cells); skips control chars |
| Color/padding | Pads on post-`chalk` length → header is ANSI-byte-count wider than box → ragged | Pads pre-color, wraps each line in ANSI after padding (gated by `NO_COLOR`/`FORCE_COLOR`/tty) |
| Empty thought | `''.padEnd(...)` works but border sized off header only | Explicitly handled: emits one empty content row |

### 3.4 Test-coverage parity

All 14 TS `it(...)` blocks have Python equivalents:

1–3. basic / optional / multi → `test_valid_basic_thought`, `test_thought_with_optional_fields`, `test_track_multiple_thoughts`
4. auto-adjust → `test_auto_adjust_total_thoughts`
5–6. branching → `test_track_two_branches`, `test_multiple_thoughts_same_branch`
7–9. edges → `test_very_long_thought_string`, `test_single_thought`, `test_next_thought_needed_false`
10–11. response shape / JSON → `test_response_format` (asserts dict keys + `json.dumps` round-trip — adapted because Python core returns a dict)
12–14. logging (regular / revision / branch) → `test_logging_emits_regular_thought`, `test_logging_emits_revision_thought`, `test_logging_emits_branch_thought`

**Python-only tests (all intentional-enhancement coverage):**

- `test_disable_thought_logging_suppresses_output`, `test_disable_thought_logging_case_insensitive`
- String-coercion suite (issue #3856): 5 tests against the pydantic arg model
- Wrapping/render suite: multi-line, long-wrap, word-boundary wrap, empty row, paragraph break, border width consistency, emoji-header regression
- Color gating: on/off, blue/yellow/green per kind, `NO_COLOR`/`FORCE_COLOR`/tty detection
- `test_process_thought_sync_helper` exercising the `_process_thought_sync` wrapper

**TS assertion not mirrored:** TS asserts the returned `content[0]` has `{type:"text", text}`. Python's equivalent is implicit (FastMCP tool layer). No gap in practice.

### 3.5 Cosmetic module-level differences

All **cosmetic**:

- Shebang: `#!/usr/bin/env -S uv run --script` (Py) vs `#!/usr/bin/env node` (TS-package)
- PEP 723 metadata block at top of Py file declares `mcp>=0.1.0` + dev extras
- `argparse` imported but only used for CLI (not in TS)
- `logging.basicConfig(INFO, …)` side-effect at import time — TS has no module-level logger setup
- `_process_thought_sync` helper — Py-only test affordance, no TS counterpart
- Python uses `snake_case` method `process_thought` vs TS `processThought`; tool name `sequentialthinking` matches

---

## Recommendations

If drop-in wire-level parity with the TS release is desired, three fixes close nearly all of the gap **without an SDK bump**:

1. **Add `title` and `annotations` to `@mcp.tool`:**
   ```python
   from mcp.types import ToolAnnotations
   @mcp.tool(
       description=_SEQUENTIAL_THINKING_DESCRIPTION,
       title="Sequential Thinking",
       annotations=ToolAnnotations(
           readOnlyHint=True,
           destructiveHint=False,
           idempotentHint=True,
           openWorldHint=False,
       ),
   )
   ```
2. **Name the FastMCP server `"sequential-thinking-server"`** (optionally set an explicit `version`) so the `initialize` handshake matches.
3. **Tighten `_coerce_bool`** to reject strings other than `"true"/"false"` so pydantic v2 lax mode cannot silently swallow `1`/`"yes"`/etc. Optionally widen `_coerce_int` to accept `Number`-style strings (`"1.0"`, `"1e2"`) to match zod.

Lower-priority follow-ups:

4. Restore the `"(numeric value, e.g., 1, 2, 3)"` field descriptions on `thoughtNumber`/`totalThoughts` to preserve the #3856 prompt-level hint to string-coercing clients.
5. Match the TS error-path body shape by adding a `try/except` in `sequentialthinking` that returns `{"error": str(e), "status": "failed"}` on unhandled exceptions, so clients that `json.loads(content[0].text)` on errors don't break.
6. Add tests for half-specified branches (`branchFromThought` without `branchId` and vice versa) — both suites currently have a coverage gap here.

If you also need `structuredContent` / `outputSchema` on the wire (Finding A), that requires upgrading `mcp` past 1.9.4 or writing the tool against the lowlevel `Server` API. Everything else (`formatThought` enhancements, startup-line wording) is a deliberate or cosmetic choice and is defensible as-is.

## Appendix — audit trail

- Team: `seq-think-audit` (3 members, all Opus 4.6 / 1M context)
- Tasks: `#1 Audit input-schema & coercion fidelity vs zod`, `#2 Audit tool-return wire format & FastMCP behavior`, `#3 Audit processThought semantics & test parity` — all completed, no files edited.
- Skills used: `fuzzy-search`, `ultrathink`.
- No runtime invocation of the servers was performed; all findings are source-grounded.
