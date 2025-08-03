# Plan: Remove regex_pattern Parameter from fuzzy_search_content

## Problem Analysis

The current two-stage filtering with `regex_pattern` (ripgrep) and `fuzzy_filter` (fzf) is causing issues:

1. **Too Restrictive**: Searching for `def update_ondemand_max_spend` misses methods that might be defined as `def update_ondemand_max_spend(self, amount):` or in other formats
2. **Confusing**: Users struggle with which parameter to use for what
3. **Redundant**: The fuzzy filter can already handle most search needs
4. **Error Prone**: Requires precise regex knowledge, leading to failed searches

## Proposed Solution

Remove the `regex_pattern` parameter entirely and rely solely on fzf's fuzzy filtering capabilities. This simplifies the tool significantly while maintaining functionality.

## Benefits

1. **Simpler Mental Model**: One search parameter instead of two
2. **More Flexible**: Fuzzy search is more forgiving than regex
3. **Better Results**: Won't miss results due to overly specific regex patterns
4. **Easier for AI**: No need to construct complex regex patterns
5. **Still Powerful**: fzf supports advanced search syntax including some regex-like patterns

## Implementation Changes

### 1. Update Function Signature

```python
def fuzzy_search_content(
    fuzzy_filter: str,
    path: str = ".",
    hidden: bool = False,
    limit: int = 20,
    rg_flags: str = "",
    multiline: bool = False,
) -> dict[str, Any]:
    """Search all file contents using fuzzy filtering."""
```

### 2. Simplify Implementation

Always use "." as the ripgrep pattern (matches all lines):

```python
# Before
rg_cmd.extend([regex_pattern, search_path])

# After
rg_cmd.extend([".", search_path])  # Always search all lines
```

### 3. Update Tool Description

```python
@mcp.tool(
    description=(
        "Search file contents using fuzzy filtering.\n\n"
        "    Files → ripgrep (all lines) → fzf (fuzzy filter) → Results\n\n"
        "Args:\n"
        "  fuzzy_filter (str): Fuzzy search query. Required.\n"
        "  path (str, optional): Directory/file to search. Defaults to current dir.\n"
        "  hidden (bool, optional): Search hidden files. Default false.\n"
        "  limit (int, optional): Max results to return. Default 20.\n"
        "  rg_flags (str, optional): Extra flags for ripgrep.\n"
        "  multiline (bool, optional): Enable multiline record processing. Default false.\n\n"
        "Fuzzy Filter Syntax:\n"
        "  Basic search: 'update_ondemand_max_spend' → finds all occurrences\n"
        "  Multiple terms: 'update spend' → lines with both terms\n"
        "  OR logic: 'update | modify' → lines with either term\n"
        "  File filtering: 'test.py: update' → only in test.py files\n"
        "  Exact match: ''exact phrase'' → exact string match\n"
        "  Exclusion: 'update !test' → exclude test files\n\n"
        "Examples:\n"
        "  1. Find function definitions: fuzzy_filter=\"def update_ondemand_max_spend\"\n"
        "  2. Find TODO comments: fuzzy_filter=\"TODO implement\"\n"
        "  3. Find imports: fuzzy_filter=\"import pandas\"\n"
    )
)
```

### 4. Remove Regex-Related Code

Remove:
- `regex_pattern` parameter
- `_looks_like_regex()` checks for the pattern parameter
- Regex pattern validation/warnings
- "Pattern vs filter" confusion in documentation
- Diagnostic messages about regex patterns

Keep:
- Fuzzy filter validation
- `_looks_like_regex()` for detecting regex in fuzzy_filter (for warnings)

### 5. Update CLI

```python
# Remove --regex-pattern argument
p_content.add_argument(
    "fuzzy_filter", help="Fuzzy search query: 'TODO implement .py: !test'"
)
# Remove: p_content.add_argument("--regex-pattern", ...)
```

### 6. Simplify Examples

Before:
```bash
./mcp_fuzzy_search.py search-content "database" --regex-pattern "TODO"
```

After:
```bash
./mcp_fuzzy_search.py search-content "TODO database"
```

### 7. Update Tests

- Remove all `regex_pattern` parameters from test calls
- Update test expectations
- Remove tests specific to regex pattern functionality
- Simplify diagnostic message tests

## Migration Strategy

### For Users

1. **Documentation**: Clear migration guide showing how to convert searches
2. **Examples**: 
   - Old: `regex_pattern="def \w+", fuzzy_filter="update"`
   - New: `fuzzy_filter="def update"`

### For AI Agents

The change actually makes it easier for AI agents:
- No need to decide between parameters
- No need to construct regex patterns
- More forgiving search behavior

## Performance Considerations

- **Potential Impact**: Ripgrep will return ALL lines instead of filtered subset
- **Mitigation**: 
  - ripgrep is extremely fast even for all lines
  - fzf is optimized for filtering large inputs
  - Can add file size limits if needed
  - `rg_flags` still allows optimization (e.g., `-t py` for Python only)

## Alternative Approaches Considered

1. **Keep regex_pattern as optional**: Still confusing, doesn't solve the core issue
2. **Rename to prefix_pattern**: Still too restrictive
3. **Make regex_pattern do fuzzy search**: Would break existing behavior
4. **Add third search mode**: Even more confusing

## Rollback Plan

If issues arise:
1. Add back `regex_pattern` as optional parameter with default "."
2. Deprecation warning for a transition period
3. Eventually remove after users adapt

## Example Searches That Become Easier

### Finding Method Definitions
Before: `regex_pattern="def update_ondemand_max_spend"` (too specific, misses variations)
After: `fuzzy_filter="def update_ondemand_max_spend"` (finds all variations)

### Finding Usages
Before: Need complex regex to find all forms
After: `fuzzy_filter="update_ondemand_max_spend"` (finds definitions AND usages)

### Finding TODOs with Context
Before: `regex_pattern="TODO", fuzzy_filter="billing"`
After: `fuzzy_filter="TODO billing"` (simpler, same result)

## Success Metrics

1. **Fewer failed searches** (no more "0 matches for pattern" errors)
2. **Simpler tool usage** (one parameter instead of two)
3. **Better discoverability** (fuzzy search finds more relevant results)
4. **Reduced support questions** about parameter usage