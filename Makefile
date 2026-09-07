.PHONY: up down db-shell migrate dev format requirements

up:
	docker compose up -d

down:
	docker compose down

db-shell:
	docker exec -it congen_db psql -U postgres -d congen

migrate:
	cd apps/api && source .venv/bin/activate && alembic upgrade head

dev:
	cd apps/api && source .venv/bin/activate && uvicorn app.main:app --reload

format:
	cd apps/api && source .venv/bin/activate && ruff check --fix && black .

requirements:
	cd apps/api && source .venv/bin/activate && pip install -r requirements.txt
