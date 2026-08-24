.PHONY: dev test test-unit lint migrate

# Conforme spec 01 §3.5, os comandos rodam dentro do container `api`.

dev:
	docker compose up -d --build

test:
	docker compose exec api pytest

# Camada unitária apenas (spec 07 RF-07-05). Não depende de infraestrutura.
test-unit:
	docker compose exec api pytest tests/unit

lint:
	docker compose exec api ruff check .

migrate:
	docker compose exec api alembic upgrade head
