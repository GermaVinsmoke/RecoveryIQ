PYTHON := $(shell if [ -x services/garmin-sync/.venv/bin/python ]; then echo services/garmin-sync/.venv/bin/python; else echo python3; fi)

.PHONY: setup sync api web dev

setup:
	mkdir -p data
	cd apps/api && go mod download modernc.org/sqlite && go mod tidy
	cd apps/web && npm install
	python3 -m venv services/garmin-sync/.venv
	services/garmin-sync/.venv/bin/pip install -r services/garmin-sync/requirements.txt

sync:
	mkdir -p data
	$(PYTHON) services/garmin-sync/sync.py --days 30

api:
	cd apps/api && go mod download modernc.org/sqlite && go run .

web:
	cd apps/web && npm run dev

dev:
	$(MAKE) sync
	@bash -c 'trap "kill 0" EXIT; (cd apps/api && go mod download modernc.org/sqlite && go run .) & (cd apps/web && npm run dev) & wait'
