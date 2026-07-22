.PHONY: dev test lint migrate

# Conforme spec 01 §3.5, os comandos rodam dentro do container `api`.

dev:
	docker compose up -d --build

test:
	docker compose exec api pytest

lint:
	docker compose exec api ruff check .

migrate:
	docker compose exec api alembic upgrade head
