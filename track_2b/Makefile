.PHONY: run build test

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

# Tests sans appel à Apertus (règles Python, recherche dans les lois, lettre, parcours complet avec un
# faux Apertus). Les tests avec le vrai Apertus sont dans tests/apertus/ (voir README).
test: build
	docker run --rm $(IMAGE) sh -c 'for f in tests/test_*.py; do printf "%-32s" "$$f"; python "$$f" > /tmp/sortie.txt 2>&1 && tail -n 1 /tmp/sortie.txt || { cat /tmp/sortie.txt; exit 1; }; done'
