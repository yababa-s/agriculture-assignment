# Runs everything except the Apple-MLX LLM path: database, queries (rule planner), app, figures, tests,
# rules-only extraction. For the LLM inside Docker build with --build-arg WITH_HF=1 and run with LLM_BACKEND=hf.
FROM python:3.12-slim
ARG WITH_HF=0
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends make && rm -rf /var/lib/apt/lists/*
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt && if [ "$WITH_HF" = "1" ]; then pip install --no-cache-dir -r requirements-hf.txt; fi
COPY . .
ENV LLM_BACKEND=none PYTHONUNBUFFERED=1
RUN python scripts/fetch_artifacts.py --only database corpus
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0"]
