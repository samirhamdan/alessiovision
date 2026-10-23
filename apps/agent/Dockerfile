# Contexto de build: raiz do repositório (o workspace uv inclui o pacote contracts).
FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.11.32
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /src
COPY . .
RUN uv sync --frozen --no-dev --no-editable --package alessio-agent

RUN useradd --system --uid 10001 alessio && mkdir -p /state && chown alessio /state
USER alessio
ENV ALESSIO_STATE_DIR=/state
ENTRYPOINT ["alessio-agent"]
