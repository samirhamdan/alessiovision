# ALESSIO

Plataforma de visão computacional para segurança e operação: um agente analisa
as câmeras (na nuvem ou na rede do cliente) e envia ocorrências e métricas para
a plataforma, que as exibe num painel web. O vídeo não precisa sair da rede do
cliente.

Estado atual: **Fase 0**. O fluxo completo funciona de ponta a ponta: vídeo →
agente → ocorrência no PostgreSQL → painel. Arquitetura, decisões e próximos
passos estão em [`docs/architecture.md`](docs/architecture.md).

```
packages/contracts   protocolo versionado agente ↔ nuvem (Pydantic)
apps/agent           Agente ALESSIO (OpenCV, regras, métricas, fila local)
apps/api             plataforma (FastAPI, SQLAlchemy, Alembic, PostgreSQL)
apps/web             painel (React, TypeScript, Vite)
deploy               Docker Compose da Fase 0
```

## Rodar com Docker Compose

```sh
cp .env.example deploy/.env            # troque ALESSIO_DEMO_AGENT_TOKEN
./deploy/scripts/download-sample-video.sh
docker compose -f deploy/docker-compose.yml up --build -d
docker compose -f deploy/docker-compose.yml --profile demo run --rm agent
```

Painel: <http://localhost:8080> · API: <http://localhost:8000/docs>

O agente de demonstração reproduz `deploy/data/demo.avi` como se fosse uma
câmera, com o primeiro quadro numa sexta às 23:00. Como a regra de
demonstração considera expediente de segunda a sexta, das 08:00 às 18:00, as
pessoas no vídeo geram uma ocorrência de "presença fora do horário". Use
`ALESSIO_REALTIME=true` para reproduzir no ritmo real e acompanhar o painel.

## Desenvolvimento local

Requisitos: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22 e PostgreSQL 16.

```sh
uv sync                                         # instala os três pacotes Python
export ALESSIO_DATABASE_URL=postgresql+psycopg://alessio:alessio@localhost:5432/alessio
export ALESSIO_DASHBOARD_ORG_ID=00000000-0000-4000-8000-000000000001
export ALESSIO_DEMO_AGENT_TOKEN=alg_dev-token

(cd apps/api && uv run alembic upgrade head)
uv run python -m alessio_api.seed
uv run uvicorn alessio_api.main:app --reload    # http://localhost:8000

echo '{"demo": "deploy/data/demo.avi"}' > sources.json
uv run alessio-agent --token alg_dev-token --sources sources.json \
    --replay-start 2026-10-23T23:00:00-03:00

(cd apps/web && npm install && npm run dev)     # http://localhost:5173
```

Para uma câmera real, aponte o `source_ref` para uma URL RTSP no `sources.json`
local do agente (ex.: `{"demo": "rtsp://usuario:senha@10.0.0.20:554/stream2"}`;
prefira o substream). Essa URL nunca é enviada à nuvem.

## Testes

```sh
uv run ruff check . && uv run ruff format --check .
uv run pytest                    # testes da API usam ALESSIO_TEST_DATABASE_URL
(cd apps/web && npm run build)
```

Os testes da API rodam contra um PostgreSQL real e criam o esquema pelas
migrações Alembic. Por padrão usam
`postgresql+psycopg://alessio:alessio@localhost:5432/alessio_test`. Sem banco
disponível, esses testes são ignorados localmente; no CI
(`ALESSIO_REQUIRE_DB=1`), a ausência do banco é falha. O teste
`apps/api/tests/test_end_to_end.py` roda o agente real contra a API real.

## Detector e licenças

O detector padrão é o HOG do OpenCV (Apache-2.0): sem download de modelo e sem
risco de licença, mas com baixa precisão. O extra opcional `ultralytics`
(`uv sync --package alessio-agent --extra ultralytics`, depois `--detector ultralytics`) é AGPL-3.0 e
serve apenas para avaliação interna até a decisão D1 em
[`docs/architecture.md`](docs/architecture.md).
