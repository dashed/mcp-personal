.PHONY: help install install-dev test test-simple test-full test-cli test-watch test-cov lint format type-check clean run debug setup check all

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := uv run python
PYTEST := uv run pytest
TEST_PATH := tests
SRC_FILES := mcp_fd_server.py
COV_REPORT := htmlcov

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install production dependencies
	uv sync --no-dev

install-dev: ## Install all dependencies including dev
	uv sync

setup: install-dev ## Full project setup (alias for install-dev)

test: ## Run all tests
	PYTHONPATH=. $(PYTEST) $(TEST_PATH) -v

test-simple: ## Run only simple/direct function tests
	PYTHONPATH=. $(PYTEST) $(TEST_PATH)/test_simple.py -v

test-full: ## Run full integration tests with async support
	PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD="" $(PYTEST) $(TEST_PATH)/test_fd_server.py -v

test-cli: ## Run CLI tests
	PYTHONPATH=. $(PYTEST) $(TEST_PATH)/test_cli.py -v

test-watch: ## Run tests in watch mode (requires pytest-watch)
	@if ! uv run pip show pytest-watch > /dev/null 2>&1; then \
		echo "Installing pytest-watch..."; \
		uv add --dev pytest-watch; \
	fi
	PYTHONPATH=. uv run ptw $(TEST_PATH) -- -v

test-cov: ## Run tests with coverage report
	PYTHONPATH=. $(PYTEST) --cov=mcp_fd_server --cov-report=html --cov-report=term $(TEST_PATH)
	@echo "Coverage report generated in $(COV_REPORT)/"

lint: ## Run linting checks
	@echo "Running ruff check..."
	@if command -v ruff > /dev/null 2>&1; then \
		uv run ruff check $(SRC_FILES); \
	else \
		echo "Installing ruff..."; \
		uv add --dev ruff; \
		uv run ruff check $(SRC_FILES); \
	fi

format: ## Format code with ruff
	@echo "Formatting code..."
	@if command -v ruff > /dev/null 2>&1; then \
		uv run ruff format $(SRC_FILES); \
	else \
		echo "Installing ruff..."; \
		uv add --dev ruff; \
		uv run ruff format $(SRC_FILES); \
	fi

type-check: ## Run type checking with pyright
	@echo "Running type checks..."
	@if command -v pyright > /dev/null 2>&1; then \
		uv run pyright $(SRC_FILES); \
	else \
		echo "Installing pyright..."; \
		uv add --dev pyright; \
		uv run pyright $(SRC_FILES); \
	fi

check: lint type-check test ## Run all checks (lint, type-check, test)

clean: ## Clean up generated files
	rm -rf $(COV_REPORT)
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .mypy_cache
	rm -rf __pycache__
	rm -rf **/__pycache__
	rm -rf *.pyc
	rm -rf **/*.pyc
	rm -rf .coverage
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info

run: ## Run the MCP server in stdio mode
	./mcp_fd_server.py

debug: ## Run with debug logging
	FASTMCP_DEBUG=true FASTMCP_LOG_LEVEL=DEBUG ./mcp_fd_server.py

# Development shortcuts
dev: install-dev ## Alias for install-dev

# CI/CD targets
ci: clean check ## Run CI pipeline (clean, then all checks)

# Quick test during development
qt: test-simple ## Quick test (alias for test-simple)

# Check if required binaries are available
check-deps: ## Check if fd and fzf are installed
	@echo "Checking for required binaries..."
	@which fd > /dev/null 2>&1 && echo "✓ fd is installed" || echo "✗ fd is not installed"
	@which fzf > /dev/null 2>&1 && echo "✓ fzf is installed" || echo "✗ fzf is not installed"

# Build distribution
build: clean ## Build distribution packages
	uv build

# All-in-one command for a full check
all: clean install-dev check ## Clean, install, and run all checks