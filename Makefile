.DEFAULT_GOAL := help
.PHONY: help setup deps build run dev config-check test fmt lint

help:
	@echo 'setup        Install locked Python dependencies into .venv'
	@echo 'config-check Validate public configuration (foundation only)'
	@echo 'run / dev    Write a foundation run; no retrieval or training'
	@echo 'test         Run unit and CLI integration tests'
	@echo 'fmt / lint   Format / check Python code'
	@echo 'build        Build wheel and source distribution'

setup deps:
	uv sync --locked

config-check:
	uv run --locked parts-search config-check

run dev:
	uv run --locked parts-search bootstrap

test:
	uv run --locked python -m unittest discover -s tests -v

fmt:
	uv run --locked ruff check --select I --fix src tests
	uv run --locked ruff format src tests

lint:
	uv run --locked ruff check src tests
	uv run --locked ruff format --check src tests

build:
	uv build
