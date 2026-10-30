BASE_URL ?= http://localhost:8080/benchmark

.PHONY: up down logs test smoke aa full
up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f benchmark

test:
	python3 -m unittest discover -s controller/tests -p 'test_*.py'

smoke:
	curl -fsS -X POST -H 'Content-Type: application/json' --data @configs/smoke.json $(BASE_URL)/api/experiments

aa:
	curl -fsS -X POST -H 'Content-Type: application/json' --data @configs/aa.json $(BASE_URL)/api/experiments

full:
	curl -fsS -X POST -H 'Content-Type: application/json' --data @configs/full.json $(BASE_URL)/api/experiments
