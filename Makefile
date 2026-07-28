# Canonical task runner. `make` is what a reviewer will type.
#
# NOTE for the Windows dev machine: `make` is not installed there. A no-dependency shim
# exists — `python tasks.py <target>` runs the same commands. See README.md.

.PHONY: help setup lint typecheck test test-fast reproduce clean splits baselines paper

PY := python
PKG := src/ecopulse_ca

help:
	@echo "setup      - create pinned venv and install (uv preferred)"
	@echo "lint       - ruff check + format check"
	@echo "typecheck  - mypy"
	@echo "test       - full pytest suite"
	@echo "test-fast  - pytest excluding network + slow"
	@echo "splits     - build and freeze benchmark splits"
	@echo "baselines  - run credential-free baseline ladder (5 seeds)"
	@echo "paper      - regenerate all figures and tables"
	@echo "reproduce  - clean-checkout end-to-end regeneration of every reported number"

setup:
	uv venv --python 3.12 && uv pip install -e ".[dev]"

lint:
	ruff check . && ruff format --check .

typecheck:
	mypy $(PKG)

test:
	pytest

test-fast:
	pytest -m "not network and not slow"

splits:
	$(PY) -m ecopulse_ca.splits.builder --freeze

baselines:
	$(PY) -m ecopulse_ca.tasks.forecasting --all-seeds
	$(PY) -m ecopulse_ca.tasks.nowcasting  --all-seeds

paper:
	$(PY) paper/scripts/build_all.py

# The single command that must regenerate every number in the paper from a clean checkout.
# Order matters: splits are frozen and hash-verified BEFORE any model sees data.
reproduce: lint typecheck test splits baselines paper
	@echo "reproduce: complete. Verify benchmark/splits/splits.sha256 is unchanged."

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__
