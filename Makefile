.PHONY: dev api web test check eval

dev:
	docker compose up --build

api:
	cd api && uv run fastapi dev main.py

web:
	cd web && npm run dev

test:
	cd api && uv run pytest
	cd web && npm test

check:
	cd api && uv run ruff check .
	cd web && npm run lint && npm run build

eval:
	cd api && uv run python -m scripts.evaluate
