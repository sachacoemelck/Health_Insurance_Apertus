.PHONY: run build

# Starts the project in a Docker container. It must work from a clean checkout.
# L'app Streamlit est ensuite ouverte sur http://localhost:8501
IMAGE := health-insurance-apertus
PORT := 8501

# Variables LLM_* : lues depuis .env s'il existe (passé au lancement, jamais copié dans
# l'image), sinon reprises du terminal (copie neuve du repo, sans .env).
ENV := $(if $(wildcard .env),--env-file .env,-e LLM_NAME -e LLM_BASE_URL -e LLM_API_KEY -e LLM_NAME_RESTITUTION)

run: build
	docker run --rm -p $(PORT):8501 $(ENV) $(IMAGE)

build:
	docker build -t $(IMAGE) .
