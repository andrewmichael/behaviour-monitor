.PHONY: help venv install install-dev install-test test test-cov test-watch lint format clean clean-all

# Default Python version
PYTHON := python3
VENV := venv
BIN := $(VENV)/bin
PYTHON_VENV := $(BIN)/python
PIP := $(BIN)/pip

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(GREEN)Behaviour Monitor - Development Commands$(NC)"
	@echo ""
	@echo "$(YELLOW)Usage:$(NC)"
	@echo "  make [target]"
	@echo ""
	@echo "$(YELLOW)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'

venv: ## Create Python virtual environment
	@if [ ! -d "$(VENV)" ]; then \
		echo "$(GREEN)Creating virtual environment...$(NC)"; \
		$(PYTHON) -m venv $(VENV); \
		echo "$(GREEN)Virtual environment created at ./$(VENV)$(NC)"; \
	else \
		echo "$(YELLOW)Virtual environment already exists$(NC)"; \
	fi

install: venv ## Install all dependencies (dev + test + runtime)
	@echo "$(GREEN)Installing development dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	@echo "$(GREEN)Dependencies installed successfully$(NC)"

install-dev: install ## Alias for 'install' (backward compatibility)

install-test: venv ## Install only test dependencies
	@echo "$(GREEN)Installing test dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-test.txt
	@echo "$(GREEN)Test dependencies installed successfully$(NC)"

test: ## Run all tests
	@echo "$(GREEN)Running tests...$(NC)"
	$(PYTHON_VENV) -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	$(PYTHON_VENV) -m pytest tests/ \
		--cov=custom_components/behaviour_monitor \
		--cov-report=term-missing \
		--cov-report=html \
		-v
	@echo ""
	@echo "$(GREEN)Coverage report generated at htmlcov/index.html$(NC)"

test-watch: ## Run tests in watch mode (requires pytest-watch)
	@echo "$(GREEN)Running tests in watch mode...$(NC)"
	$(PYTHON_VENV) -m pytest_watch tests/ -v

test-sensor: ## Run only sensor tests
	@echo "$(GREEN)Running sensor tests...$(NC)"
	$(PYTHON_VENV) -m pytest tests/test_sensor.py -v

test-init: ## Run only init tests
	@echo "$(GREEN)Running init tests...$(NC)"
	$(PYTHON_VENV) -m pytest tests/test_init.py -v

test-analyzer: ## Run only analyzer tests
	@echo "$(GREEN)Running analyzer tests...$(NC)"
	$(PYTHON_VENV) -m pytest tests/test_analyzer.py -v

test-ml: ## Run only ML analyzer tests
	@echo "$(GREEN)Running ML analyzer tests...$(NC)"
	$(PYTHON_VENV) -m pytest tests/test_ml_analyzer.py -v

test-coordinator: ## Run only coordinator tests
	@echo "$(GREEN)Running coordinator tests...$(NC)"
	$(PYTHON_VENV) -m pytest tests/test_coordinator.py -v

test-config: ## Run only config flow tests
	@echo "$(GREEN)Running config flow tests...$(NC)"
	$(PYTHON_VENV) -m pytest tests/test_config_flow.py -v

lint: ## Run linters (ruff, mypy)
	@echo "$(GREEN)Running ruff...$(NC)"
	-$(PYTHON_VENV) -m ruff check custom_components/ tests/
	@echo "$(GREEN)Running mypy...$(NC)"
	-$(PYTHON_VENV) -m mypy custom_components/behaviour_monitor/

format: ## Format code with black and ruff
	@echo "$(GREEN)Formatting code with black...$(NC)"
	$(PYTHON_VENV) -m black custom_components/ tests/
	@echo "$(GREEN)Running ruff --fix...$(NC)"
	$(PYTHON_VENV) -m ruff check --fix custom_components/ tests/

check: lint test ## Run linters and tests

clean: ## Clean up Python cache files and test artifacts
	@echo "$(YELLOW)Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.py,cover" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.xml
	@echo "$(GREEN)Cleanup complete$(NC)"

clean-all: clean ## Clean everything including virtual environment
	@echo "$(YELLOW)Removing virtual environment...$(NC)"
	rm -rf $(VENV)
	@echo "$(GREEN)Full cleanup complete$(NC)"

activate: ## Show command to activate virtual environment
	@echo ""
	@echo "$(GREEN)To activate the virtual environment, run:$(NC)"
	@echo "  source $(VENV)/bin/activate"
	@echo ""
	@echo "$(GREEN)To deactivate, run:$(NC)"
	@echo "  deactivate"
	@echo ""

# Development workflow targets
dev-setup: install ## Complete development setup
	@echo ""
	@echo "$(GREEN)✓ Development environment ready!$(NC)"
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Activate the virtual environment:"
	@echo "     source $(VENV)/bin/activate"
	@echo ""
	@echo "  2. Run tests:"
	@echo "     make test"
	@echo ""
	@echo "  3. Run tests with coverage:"
	@echo "     make test-cov"
	@echo ""
	@echo "For more commands, run: make help"
	@echo ""

# Quick shortcuts
t: test ## Shortcut for 'test'
tc: test-cov ## Shortcut for 'test-cov'
l: lint ## Shortcut for 'lint'
f: format ## Shortcut for 'format'
