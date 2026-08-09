FROM registry.access.redhat.com/ubi10:1785332448

USER 0

WORKDIR /app

ENV LOG_DIR=/app/logs/ \
    DATA_DIR=/app/data/reports \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KUBEOPTIX_API_HOST=0.0.0.0 \
    KUBEOPTIX_API_PORT=8000 \
    LOG_LEVEL=INFO

RUN dnf install -y \
    python3 \
    python3-pip \
    && dnf clean all \
    && mkdir -p "$LOG_DIR" "$DATA_DIR" \
    && chgrp -R 0 /app \
    && chmod -R g=u /app

COPY requeriments.txt /app/requeriments.txt

RUN python3 -m pip install --no-cache-dir -r /app/requeriments.txt

COPY src/ /app/src/

RUN chgrp -R 0 /app \
    && chmod -R g=u /app

USER 1001

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]



