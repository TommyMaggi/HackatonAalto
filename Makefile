.PHONY: setup check validate gate examples run clean

PY ?= python3

setup:
	$(PY) -m pip install -q jsonschema pyyaml duckdb
	@mkdir -p artifacts
	@cp -n artifacts/examples/*.json artifacts/ 2>/dev/null || true
	@cp -n artifacts/examples/decision_log.jsonl artifacts/ 2>/dev/null || true
	@echo "ready — example artifacts copied into artifacts/, build against those"

check: gate validate

validate:
	@$(PY) tools/validate.py

examples:
	@$(PY) tools/validate.py --examples

gate:
	@$(PY) tools/gate_check.py

run:
	$(PY) -m pipeline.run --config config/llm.yaml

clean:
	@rm -f artifacts/*.json artifacts/*.jsonl
	@find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "artifacts cleared"
