#!/usr/bin/env python
"""Debug the actual PDF test scenario on Windows."""

import asyncio
import json
import sys
import platform
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

print(f"Platform: {platform.system()}")
print(f"Python: {sys.version}")

# Import the modules
import mcp_fuzzy_search
from mcp.shared.memory import create_connected_server_and_client_session as client_session

async def test_scenario():
    """Simulate the test scenario."""
    print("\n=== Running test scenario ===")
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create a mock PDF file
        test_pdf = tmp_path / "test.pdf"
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n203\n%%EOF"
        test_pdf.write_bytes(pdf_content)
        
        # Set up mocks
        mock_rga_output = (
            '{"type":"match","data":{"path":{"text":"'
            + str(test_pdf)
            + '"},"lines":{"text":"Page 1: This is test content"},"line_number":null,"absolute_offset":100,"submatches":[{"match":{"text":"test"},"start":8,"end":12}]}}\n'
            + '{"type":"end","data":{"path":{"text":"'
            + str(test_pdf)
            + '"},"binary_offset":null,"stats":{"elapsed":{"secs":0,"nanos":35222125,"human":"0.035222s"},"searches":1,"searches_with_match":1,"bytes_searched":1000,"bytes_printed":100,"matched_lines":1,"matches":1}}}'
        )
        
        # Mock objects for subprocess.run
        mock_run_rga = MagicMock()
        mock_run_rga.returncode = 0
        mock_run_rga.stdout = mock_rga_output
        mock_run_rga.stderr = ""
        
        mock_run_fzf = MagicMock()
        mock_run_fzf.returncode = 0
        mock_run_fzf.stdout = f"{test_pdf}:0:Page 1: This is test content"
        mock_run_fzf.stderr = None
        
        # Try mocking at different levels
        print("\n1. Testing with subprocess.run mock:")
        with patch("subprocess.run", side_effect=[mock_run_rga, mock_run_fzf]) as mock_run:
            try:
                # Call the function directly
                result = mcp_fuzzy_search.fuzzy_search_documents(
                    fuzzy_filter="test",
                    path=str(tmp_path),
                    limit=10
                )
                print(f"Direct call result: {json.dumps(result, indent=2)}")
                print(f"Mock called: {mock_run.called}")
                print(f"Mock call count: {mock_run.call_count}")
            except Exception as e:
                print(f"Error with subprocess.run mock: {e}")
        
        print("\n2. Testing with mcp_fuzzy_search.subprocess.run mock:")
        with patch("mcp_fuzzy_search.subprocess.run", side_effect=[mock_run_rga, mock_run_fzf]) as mock_run:
            try:
                result = mcp_fuzzy_search.fuzzy_search_documents(
                    fuzzy_filter="test",
                    path=str(tmp_path),
                    limit=10
                )
                print(f"Direct call result: {json.dumps(result, indent=2)}")
                print(f"Mock called: {mock_run.called}")
                print(f"Mock call count: {mock_run.call_count}")
            except Exception as e:
                print(f"Error with mcp_fuzzy_search.subprocess.run mock: {e}")
        
        # Check if Windows debug mode is enabled
        print(f"\n3. Checking Windows debug mode detection:")
        print(f"platform.system() == 'Windows': {platform.system() == 'Windows'}")
        print(f"os.environ.get('GITHUB_ACTIONS'): {os.environ.get('GITHUB_ACTIONS')}")
        
        # Check subprocess.Popen mock detection
        print(f"\n4. Checking subprocess.Popen type:")
        import subprocess
        print(f"subprocess.Popen type: {type(subprocess.Popen)}")
        print(f"'MagicMock' in str(type(subprocess.Popen)): {'MagicMock' in str(type(subprocess.Popen))}")
        print(f"'Mock' in str(type(subprocess.Popen)): {'Mock' in str(type(subprocess.Popen))}")

# Run the test
import os
if __name__ == "__main__":
    asyncio.run(test_scenario())