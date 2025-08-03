#!/bin/bash

# Tmux helper script for Windows VM debugging

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

case "$1" in
    attach)
        echo -e "${GREEN}Attaching to windebug tmux session...${NC}"
        tmux attach-session -t windebug
        ;;
    
    new)
        echo -e "${YELLOW}Creating new windebug tmux session...${NC}"
        tmux kill-session -t windebug 2>/dev/null
        tmux new-session -d -s windebug "ssh -i ~/.ssh/azure_win_vm alberto@4.206.155.11"
        echo -e "${GREEN}Session created! Use './windebug-tmux.sh attach' to connect${NC}"
        ;;
    
    send)
        if [ -z "$2" ]; then
            echo -e "${YELLOW}Usage: $0 send 'command'${NC}"
            exit 1
        fi
        echo -e "${CYAN}Sending command to windebug session: $2${NC}"
        tmux send-keys -t windebug "$2" Enter
        ;;
    
    status)
        echo -e "${CYAN}Tmux sessions:${NC}"
        tmux list-sessions | grep windebug || echo "No windebug session found"
        ;;
    
    setup-windows)
        echo -e "${GREEN}Sending Windows setup commands...${NC}"
        # Fix PATH
        tmux send-keys -t windebug '$env:Path = "C:\ProgramData\chocolatey\bin;C:\Program Files\Git\cmd;C:\Python312;C:\Python312\Scripts;" + $env:Path' Enter
        sleep 1
        
        # Clone repository
        tmux send-keys -t windebug 'cd C:\' Enter
        tmux send-keys -t windebug 'git clone https://github.com/dashed/mcp-personal.git' Enter
        sleep 3
        
        # Navigate to repo
        tmux send-keys -t windebug 'cd C:\mcp-personal' Enter
        
        echo -e "${GREEN}Setup commands sent! Attach to see progress.${NC}"
        ;;
    
    run-tests)
        echo -e "${GREEN}Running PDF tests on Windows...${NC}"
        tmux send-keys -t windebug 'cd C:\mcp-personal' Enter
        tmux send-keys -t windebug 'python -m pytest -xvs tests/test_fuzzy_search.py::test_fuzzy_search_documents_basic' Enter
        echo -e "${GREEN}Test command sent! Attach to see results.${NC}"
        ;;
    
    *)
        echo -e "${CYAN}Windows VM Debugging Tmux Helper${NC}"
        echo -e "${YELLOW}Usage:${NC}"
        echo "  $0 attach        - Attach to existing session"
        echo "  $0 new           - Create new session (kills existing)"
        echo "  $0 send 'cmd'    - Send command to session"
        echo "  $0 status        - Show session status"
        echo "  $0 setup-windows - Send setup commands to Windows"
        echo "  $0 run-tests     - Run failing PDF tests"
        ;;
esac