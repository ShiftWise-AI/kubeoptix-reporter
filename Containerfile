FROM registry.access.redhat.com/ubi10:1785332448

USER 0

WORKDIR /app

ENV LOG_DIR=/app/logs/ \
    DATA_DIR=/app/data/reports \
    PUPPETEER_CACHE_DIR=/app/.cache/puppeteer \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KUBEOPTIX_API_HOST=0.0.0.0 \
    KUBEOPTIX_API_PORT=8000 \
    LOG_LEVEL=INFO

RUN dnf install -y \
    alsa-lib \
    at-spi2-atk \
    at-spi2-core \
    atk \
    fontconfig \
    gcc \
    libXcomposite \
    libXdamage \
    libXfixes \
    libXrandr \
    libjpeg-turbo \
    libxkbcommon \
    mesa-libgbm \
    nodejs \
    nspr \
    nss \
    pango \
    python3 \
    python3-pip \
    ruby \
    ruby-devel \
    rubygems \
    make \
    unzip \
    && dnf clean all \
    && mkdir -p "$LOG_DIR" "$DATA_DIR" \
    && chgrp -R 0 /app \
    && chmod -R g=u /app

COPY requeriments.txt /app/requeriments.txt

RUN python3 -m pip install --no-cache-dir -r /app/requeriments.txt

RUN gem install asciidoctor-pdf rouge --no-document

RUN npm install --global @mermaid-js/mermaid-cli@11.16.0

COPY src/ /app/src/
COPY template/ /app/template/
COPY wrapper/ /app/wrapper/

RUN chgrp -R 0 /app \
    && chmod -R g=u /app

USER 1001

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]



