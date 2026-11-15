# syntax=docker/dockerfile:1
# The workflow service, and the extraction worker (same image, different command).
#   docker build -f deploy/docker/workflow.Dockerfile -t priorauth-workflow workflow
#   service: uvicorn (default)   worker: python -m app.worker

FROM python:3.12.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LOG_FORMAT=json

WORKDIR /srv

# Packages first, so a code change doesn't reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY rules ./rules
COPY seed ./seed

# A fixed, unprivileged user id: Kubernetes checks runAsNonRoot against a number.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

EXPOSE 8000
# Exec form, so uvicorn is PID 1 and gets the stop signal itself.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
