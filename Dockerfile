FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DECISION_DB_PATH=/state/decision.db DECISION_ARCHIVE_PATH=/state/decision_profile.json
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .
COPY app.py ./
COPY scripts ./scripts
COPY data/raw ./data/raw
COPY data/school_research_consolidated.json ./data/
COPY .streamlit ./.streamlit
RUN useradd --create-home appuser && mkdir /state && chown appuser:appuser /state
USER appuser
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=3)"
CMD ["sh", "-c", "python scripts/bootstrap.py --skip-projection && exec streamlit run app.py --server.address=0.0.0.0"]
