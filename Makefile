# Canonical task runner. `make` is what a reviewer will type.
#
# Every target delegates to tasks.py, which holds the single definition of what each one
# runs. The two used to repeat each other and drifted: the `paper` target gained producer
# scripts on one side only. Delegation makes that class of bug impossible rather than
# merely tested for.
#
# `make` is not installed on the Windows dev machine. The same targets run there with
# `python tasks.py <target>` — identical commands, since both go through the same table.

.PHONY: help setup lint typecheck test test-fast reproduce clean splits baselines paper

PY := python

help:
	@echo "setup      - create the pinned 3.12 venv and install (works with or without uv)"
	@echo "lint       - ruff check + format check"
	@echo "typecheck  - mypy"
	@echo "test       - full pytest suite"
	@echo "test-fast  - pytest excluding network + slow"
	@echo "splits     - build and freeze benchmark splits"
	@echo "baselines  - run credential-free baseline ladder (5 seeds)"
	@echo "paper      - regenerate every table and re-render the manuscript"
	@echo "reproduce  - clean-checkout end-to-end regeneration of every reported number"

setup:
	$(PY) tasks.py setup

lint:
	$(PY) tasks.py lint

typecheck:
	$(PY) tasks.py typecheck

test:
	$(PY) tasks.py test

test-fast:
	$(PY) tasks.py test-fast

splits:
	$(PY) tasks.py splits

baselines:
	$(PY) tasks.py baselines

paper:
	$(PY) tasks.py paper

# The single command that must regenerate every number in the paper from a clean checkout.
# Order matters: splits are frozen and hash-verified BEFORE any model sees data.
reproduce: lint typecheck test splits baselines paper
	@echo "reproduce: complete. Verify benchmark/splits/splits.sha256 is unchanged."

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__
