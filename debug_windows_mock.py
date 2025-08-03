#!/usr/bin/env python
"""Debug why subprocess.run mocks aren't working on Windows."""

import subprocess
import sys
import platform
from unittest.mock import patch, MagicMock

print(f"Platform: {platform.system()}")
print(f"Python: {sys.version}")

# Test 1: Basic subprocess.run mock
print("\n=== Test 1: Basic subprocess.run mock ===")
with patch("subprocess.run") as mock_run:
    mock_run.return_value = MagicMock(returncode=0, stdout="mocked output")
    
    # Call subprocess.run
    result = subprocess.run(["echo", "test"], capture_output=True, text=True)
    
    print(f"Mock called: {mock_run.called}")
    print(f"Call count: {mock_run.call_count}")
    if mock_run.called:
        print(f"Call args: {mock_run.call_args}")
    print(f"Result stdout: {result.stdout}")

# Test 2: Check how mcp_fuzzy_search imports subprocess
print("\n=== Test 2: Module import check ===")
import mcp_fuzzy_search
print(f"mcp_fuzzy_search.__file__: {mcp_fuzzy_search.__file__}")
print(f"subprocess module id in main: {id(subprocess)}")
print(f"subprocess module in sys.modules: {id(sys.modules['subprocess'])}")

# Check if mcp_fuzzy_search has its own subprocess reference
if hasattr(mcp_fuzzy_search, 'subprocess'):
    print(f"mcp_fuzzy_search has subprocess attribute")
    print(f"subprocess module id in mcp_fuzzy_search: {id(mcp_fuzzy_search.subprocess)}")
else:
    print("mcp_fuzzy_search does not have subprocess attribute")

# Test 3: Mock at the mcp_fuzzy_search level
print("\n=== Test 3: Mock at mcp_fuzzy_search level ===")
with patch("mcp_fuzzy_search.subprocess.run") as mock_run:
    mock_run.return_value = MagicMock(returncode=0, stdout="mocked at module level")
    
    # Test if the fuzzy_search_documents function would use the mock
    # We can't actually call it without proper setup, but we can check the mock setup
    print(f"Mock object: {mock_run}")
    print(f"Mock successfully created at mcp_fuzzy_search.subprocess.run")

print("\n=== Debug complete ===")