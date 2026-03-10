.PHONY: help setup up down logs migrate ollama test

help:
	@echo "CV Conformity Agent — Comandos disponíveis:"
	@echo "  make setup      - Setup completo do projeto"
	@echo "  make up         - Sobe todos os containers"
	@echo "  make down       - Derruba os containers"
	@echo "  make logs       - Logs dos containers"
	@echo "  make migrate    - Roda as migrations do banco"
	@echo "  make ollama     - Baixa o modelo llama3.1:8b"
	@echo "  make test       - Roda os testes"
	@echo "  make ui         - Sobe o Streamlit"
	@echo "  make api        - Sobe a FastAPI"

setup:
	cp .env.example .env
	python -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	make up
	sleep 5
	make migrate
	make ollama
	@echo "✅ Setup completo! Acesse:"
	@echo "   pgAdmin  → http://localhost:5050"
	@echo "   ChromaDB → http://localhost:8001"
	@echo "   API      → http://localhost:8000/docs"

up:
	docker compose up -d
	@echo "✅ Containers rodando"

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	alembic upgrade head
	@echo "✅ Migrations aplicadas"

ollama:
	ollama pull llama3.1:8b
	@echo "✅ Modelo llama3.1:8b pronto"

test:
	pytest tests/ -v --cov=. --cov-report=term-missing

ui:
	streamlit run ui/app.py

api:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000