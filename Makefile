.DEFAULT_GOAL := help
.PHONY: help setup deps build run dev config-check stages pipeline activate rollback test test-all fmt lint

help:
	@echo 'setup        Install locked Python dependencies into .venv'
	@echo 'config-check Validate public configuration (foundation only)'
	@echo 'run / dev    Write a foundation run; no retrieval or training'
	@echo 'stages       List Golden Path stages and their config dependencies'
	@echo 'pipeline     Run every stage (exit 2=blocked, 3=incomplete, 4=not accepted)'
	@echo 'activate     Point active.json at a promoted release'
	@echo 'rollback     Restore the previous active release'
	@echo 'test         Run unit and CLI tests (real-service tests are excluded)'
	@echo 'test-all     Also run tests marked integration (needs local services)'
	@echo 'fmt / lint   Format / check Python code'
	@echo 'build        Build wheel and source distribution'

setup deps:
	uv sync --locked

config-check:
	uv run --locked parts-search config-check

run dev:
	uv run --locked parts-search bootstrap

# stdout を純 JSON に保つため make のレシピ echo を抑制する（`make stages | jq` 用）
stages:
	@uv run --locked parts-search stages

# 0 になるのは release が promote し smoke まで通ったときだけ。
# 2=blocked / 3=incomplete / 4=品質不採用（実行は成功）。
pipeline:
	@uv run --locked parts-search pipeline

# Usage: make activate RELEASE=artifacts/releases/<run-id>
activate:
	@test -n "$(RELEASE)" || (echo "RELEASE is required" >&2; exit 2)
	uv run --locked parts-search activate "$(RELEASE)"

rollback:
	uv run --locked parts-search rollback

# 既定は実接続を含めない。marker で分離している理由は pyproject の pytest 設定を参照。
test:
	uv run --locked pytest

test-all:
	uv run --locked pytest -m ''

fmt:
	uv run --locked ruff check --select I --fix src tests
	uv run --locked ruff format src tests

lint:
	uv run --locked ruff check src tests
	uv run --locked ruff format --check src tests

build:
	uv build
