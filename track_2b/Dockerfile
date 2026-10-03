FROM python:3.12-slim

# Pas de fichiers .pyc, journaux Python affichés immédiatement, pas de statistiques Streamlit
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uniquement ce dont l'app a besoin. Le .env n'est jamais copié (voir aussi .dockerignore) :
# les variables LLM_* sont fournies au lancement (make run -> docker run --env-file .env).
COPY .streamlit/ .streamlit/
COPY src/ src/
COPY data/ data/

# L'app tourne sans droits d'administration
RUN useradd --create-home appuser
USER appuser

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

# 0.0.0.0 : accessible depuis l'extérieur du conteneur (remplace address = "localhost"
# de .streamlit/config.toml, prévu pour le lancement en local)
CMD ["streamlit", "run", "src/app.py", "--server.address", "0.0.0.0", "--server.port", "8501", \
     "--server.headless", "true", "--server.fileWatcherType", "none"]
