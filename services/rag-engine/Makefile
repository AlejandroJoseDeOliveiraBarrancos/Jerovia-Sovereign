# Prefer uv so local runs use the same lockfile as CI; fall back to the venv.
# Both paths need a trailing space in RUN so `$(RUN) <tool>` expands correctly.
UV := $(shell command -v uv 2>/dev/null || ([ -x .venv/bin/uv ] && echo .venv/bin/uv))
ifeq ($(UV),)
RUN := .venv/bin/
VENV_STAMP := .venv/.install-stamp
GUARD := @test -x .venv/bin/python || { printf "No environment found. Run 'make install' first.\n"; exit 1; }
else
RUN := $(UV) run
VENV_STAMP :=
GUARD :=
endif

COMPOSE ?= docker compose

.DEFAULT_GOAL := help
.PHONY: help install sync lock lint format format-check typecheck test test-cov check \
        pre-commit ci up down logs ps rebuild clean

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: $(VENV_STAMP) ## Create the environment and install runtime + dev dependencies

$(VENV_STAMP): pyproject.toml
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"
	.venv/bin/python -m pip install uv
	touch $(VENV_STAMP)

sync: ## Re-sync the environment from pyproject.toml and uv.lock
	@test -n "$(UV)" || $(MAKE) --no-print-directory install
	$(UV) sync --frozen --all-extras

lock: ## Refresh uv.lock from pyproject.toml
	@test -n "$(UV)" || $(MAKE) --no-print-directory install
	$(UV) lock

lint: ## Lint with ruff
	$(GUARD)
	$(RUN) ruff check src tests

format: ## Format code and sort imports with ruff
	$(GUARD)
	$(RUN) ruff format src tests
	$(RUN) ruff check --fix --select I src tests

format-check: ## Verify formatting without writing
	$(GUARD)
	$(RUN) ruff format --check src tests
	$(RUN) ruff check --select I --diff src tests

typecheck: ## Static type check with mypy (strict)
	$(GUARD)
	$(RUN) mypy

test: ## Run the unit test suite
	$(GUARD)
	$(RUN) pytest

test-cov: ## Run the unit test suite with a coverage report
	$(GUARD)
	$(RUN) pytest --cov --cov-report=term-missing --cov-report=xml

check: lint format-check typecheck test ## Gate used by CI: lint, format, types, tests
	@echo "make check: OK"

pre-commit: ## Install the pre-commit hooks into the repo's .git/hooks
	$(GUARD)
	$(RUN) pre-commit install --config "$(CURDIR)/.pre-commit-config.yaml"

ci: check ## Local dry run of the CI gate

up: ## Start Postgres and the app (docker compose)
	$(COMPOSE) up -d --wait

down: ## Stop and remove the compose stack
	$(COMPOSE) down

ps: ## Show compose service status
	$(COMPOSE) ps

logs: ## Tail compose logs
	$(COMPOSE) logs -f --tail=100

rebuild: ## Rebuild the app image and restart the stack
	$(COMPOSE) up -d --build --wait

clean: ## Remove caches, build artifacts and the virtualenv
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache build dist coverage.xml htmlcov
	find . -path ./.venv -prune -o -name '__pycache__' -type d -print0 | xargs -0 rm -rf