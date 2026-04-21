PYTHON ?= python3
PYTHONPATH ?= packages/aether_core/src:.

.PHONY: test lint format run-ingestion run-fusion run-memory run-reasoning run-governance run-action run-realtime run-kernel start demo stop logs

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m compileall packages services tests

run-ingestion:
	PYTHONPATH=$(PYTHONPATH) uvicorn services.ingestion.app.main:app --host 0.0.0.0 --port 8001 --reload

run-fusion:
	PYTHONPATH=$(PYTHONPATH) uvicorn services.fusion.app.main:app --host 0.0.0.0 --port 8002 --reload

run-memory:
	PYTHONPATH=$(PYTHONPATH) uvicorn services.memory.app.main:app --host 0.0.0.0 --port 8003 --reload

run-reasoning:
	PYTHONPATH=$(PYTHONPATH) uvicorn services.reasoning.app.main:app --host 0.0.0.0 --port 8004 --reload

run-governance:
	PYTHONPATH=$(PYTHONPATH) uvicorn services.governance.app.main:app --host 0.0.0.0 --port 8005 --reload

run-action:
	PYTHONPATH=$(PYTHONPATH) uvicorn services.action.app.main:app --host 0.0.0.0 --port 8006 --reload

run-realtime:
	PYTHONPATH=$(PYTHONPATH) uvicorn services.realtime.app.main:app --host 0.0.0.0 --port 8007 --reload

run-kernel:
	PYTHONPATH=$(PYTHONPATH) uvicorn services.kernel.app.main:app --host 0.0.0.0 --port 8008 --reload

start:
	sh scripts/start-local.sh

demo:
	sh scripts/demo-local.sh

stop:
	sh scripts/stop-local.sh

logs:
	docker compose logs -f --tail=200
