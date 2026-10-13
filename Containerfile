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

RUN gem install css_parser --version 3.3.0 --no-document \
    && curl --fail --silent --show-error --location \
        https://github.com/asciidoctor/asciidoctor-pdf/archive/39a97554fbd2c27cdd919bde3091dc048b174ce6.tar.gz \
        --output /tmp/asciidoctor-pdf.tar.gz \
    && mkdir /tmp/asciidoctor-pdf \
    && tar -xzf /tmp/asciidoctor-pdf.tar.gz --strip-components=1 -C /tmp/asciidoctor-pdf \
    && cd /tmp/asciidoctor-pdf \
    && ruby -rrubygems/package -e 'spec = Gem::Specification.load("asciidoctor-pdf.gemspec"); spec.dependencies.delete_if { |dependency| dependency.name == "prawn-svg" }; spec.add_runtime_dependency "prawn-svg", "~> 0.40.4"; Gem::Package.build(spec, false, false, "/tmp/asciidoctor-pdf.gem")' \
    && gem install /tmp/asciidoctor-pdf.gem rouge --no-document \
    && rm -rf /tmp/asciidoctor-pdf /tmp/asciidoctor-pdf.tar.gz /tmp/asciidoctor-pdf.gem

COPY src/ /app/src/
COPY template/ /app/template/
COPY wrapper/ /app/wrapper/

RUN chgrp -R 0 /app \
    && chmod -R g=u /app

USER 1001

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]



