# ALESSIO — Arquitetura

Documento consolidado após três rodadas de análise (proposta original, revisão
crítica e reanálise do arquiteto). Registra as decisões tomadas, o protocolo
entre agente e nuvem e o que já foi implementado.

## 1. Visão geral

```
Câmeras IP (RTSP / ONVIF)
        │  vídeo nunca sai da rede do cliente
        ▼
Agente ALESSIO  (na nuvem para testes, ou num mini-PC no cliente)
  OpenCV · Detector intercambiável · Zonas · Regras · Métricas
  Fila local SQLite · Cache de configuração · Identidade própria
        │  HTTPS de saída, sempre iniciado pelo agente
        ▼
Plataforma ALESSIO (nuvem)
  FastAPI · PostgreSQL · Ocorrências · Métricas · (Notificações)
        │
        ▼
Painel web  ── Segurança: ocorrências e alertas
            └─ Operação: indicadores e relatórios
```

Princípios:

1. **Um único caminho de ingestão.** O processamento de vídeo é sempre o
   Agente ALESSIO, rodando onde for. Não existe API interna separada para um
   worker na nuvem.
2. **O agente não depende da plataforma.** Não instala FastAPI, não acessa o
   PostgreSQL central. O que é compartilhado fica em `packages/contracts`.
3. **A nuvem não alcança a câmera.** Toda comunicação parte do agente.
   Credenciais RTSP ficam só no agente (arquivo `sources.json` local); a nuvem
   conhece apenas um apelido (`source_ref`).
4. **Ocorrências ≠ métricas.** Segurança trabalha com ocorrências (entidades com
   início e fim). Operação trabalha com séries temporais agregadas por minuto.

## 2. Estrutura do repositório

| Caminho | Conteúdo |
| --- | --- |
| `packages/contracts` | Modelos Pydantic versionados: mensagens, configuração do agente |
| `apps/agent` | Agente: fontes de vídeo, detector, regras, métricas, fila local, envio |
| `apps/api` | Plataforma: ingestão, configuração do agente, API do painel, migrações |
| `apps/web` | Painel React + TypeScript + Vite |
| `deploy` | Docker Compose de demonstração e scripts |

O workspace Python é gerenciado com `uv` (um `uv.lock` para os três pacotes).

## 3. Decisões bloqueadoras

| # | Decisão | Situação |
| --- | --- | --- |
| D1 | Licença do detector | **Em aberto.** O agente usa a interface `Detector`. O padrão é HOG do OpenCV (Apache-2.0, baixa precisão). Ultralytics (AGPL-3.0) é um extra opcional, só para avaliação interna. Fechar com revisão jurídica **antes do primeiro agente instalado em cliente**. Alternativas Apache-2.0 a avaliar: YOLOX, RT-DETR, D-FINE, RTMDet. |
| D2 | Protocolo do agente | **Definido (v1.0)**, seção 4. |
| D3 | Definição das métricas de Operação | **Definida**, seção 5. Ocupação implementada; entradas, saídas e permanência na Fase 3. |
| D4 | Escopo do piloto | **Definido:** uma câmera, uma zona, regra `person.after_hours`, métrica de ocupação. |

## 4. Protocolo agente ↔ nuvem (v1.0)

| Método | Rota | Uso |
| --- | --- | --- |
| `POST` | `/agent/v1/enroll` | Troca o código de ativação (uso único, 24 h) pelo token do agente |
| `POST` | `/agent/v1/messages` | Lote de até 500 mensagens; idempotente por `message_id` |
| `GET` | `/agent/v1/config` | Configuração do agente; `ETag` / `If-None-Match` → `304` |
| `GET` | `/agent/v1/commands` | *(Fase 2)* long-poll de comandos: snapshot, teste, recarga |

Autenticação: `Authorization: Bearer <token do agente>`. A nuvem guarda só o
SHA-256 do token. Ciclo do agente: `pending` (código de ativação emitido) →
`active` (token emitido em `/enroll`) → `revoked`. Um novo código num agente
ativo é a rotação de credencial: o token antigo vale até o novo código ser
usado, e então deixa de valer. O agente guarda o token em
`<state-dir>/credentials.json` com permissão 0600, nunca em linha de comando.

Envelope de toda mensagem:

```json
{
  "schema_version": "1.0",
  "message_id": "uuid gerado no agente",
  "agent_session_id": "uuid da execução do agente",
  "sent_at": "2026-10-23T23:00:00Z",
  "type": "occurrence.opened",
  "payload": {}
}
```

Tipos: `occurrence.opened`, `occurrence.updated`, `occurrence.closed`,
`metrics.zone_1m`, `heartbeat`. Esquemas completos em
`packages/contracts/src/alessio_contracts/messages.py`.

Regras de processamento na nuvem:

- A **organização vem da credencial do agente**, nunca do payload. Campos
  extras (ex.: `organization_id`) são recusados pelo contrato.
- Câmeras, zonas, regras e ocorrências citadas precisam pertencer **àquele
  agente**; caso contrário a mensagem é `rejected` (as demais do lote seguem).
- `message_id` repetido → `duplicate` (o agente pode reenviar sem medo).
- Resultado por mensagem: `accepted`, `duplicate` ou `rejected` + motivo.

No agente, toda mensagem passa pela fila local SQLite antes do envio. Falha de
rede ou 5xx mantém a fila; `rejected` vai para *dead letter* (guardada para
diagnóstico, não trava a fila); um lote recusado por inteiro (422) é reenviado
uma mensagem por vez para isolar a culpada.

### Ocorrências

O agente controla o ciclo de vida, porque é ele quem vê a condição começar e
terminar:

```
ocioso ──presença fora do horário──▶ pendente ──duração mínima──▶ ativa
   ▲                                    │                          │
   └──── falha > tolerância ────────────┘     sem presença por     │
   └──────────────────────────────────────── clear_after_seconds ──┘
```

- `opened`: o agente gera o `occurrence_id`; `started_at` = primeira observação.
- `updated`: apenas quando o máximo de pessoas aumenta (volume limitado).
- `closed`: motivo `cleared`, `schedule` (começou o expediente), `signal_lost`
  ou `shutdown`.
- A nuvem faz upsert idempotente em `occurrences` e grava cada mensagem em
  `occurrence_updates` (histórico imutável).
- `state` (aberta/encerrada, do agente) e `review_status` (atendimento do
  operador) são dimensões independentes.
- A regra observa o **estado da zona** (quantas pessoas estão nela), não um
  `track_id`, para não depender da estabilidade do rastreamento.

## 5. Métricas de Operação

- **Ponto de apoio:** centro inferior da caixa da pessoa (os pés).
- **Ocupação:** pessoas com o ponto de apoio dentro do polígono, por quadro
  analisado. Por minuto: média ponderada pelo tempo (`occupancy_avg`) e pico
  (`occupancy_max`). *Implementado.*
- **Cobertura:** `analyzed_seconds` por minuto. Câmera fora do ar aparece como
  lacuna, não como "zero pessoas". *Implementado.*
- **Minutos parciais** (ex.: agente reiniciado no meio do minuto) são
  combinados na nuvem com média ponderada pelo tempo analisado. *Implementado.*
- **Entrada / saída** *(Fase 3)*: transição fora↔dentro confirmada após ~1 s
  (histerese). Quem já aparece dentro da zona conta como `appeared`.
- **Permanência** *(Fase 3)*: da entrada à saída, contabilizada no minuto da
  saída; tracks perdidos são encerrados na expiração e marcados `truncated`.
  Guardar `dwell_count`, `dwell_sum_s` e **histograma de faixas fixas**
  (0–10 s, 10–30 s, 30–60 s, 1–5 min, 5–15 min, >15 min). Percentis por
  minuto **não** são armazenados: não se agregam corretamente.

## 6. Modelo de dados

| Grupo | Tabelas |
| --- | --- |
| Identidade | `organizations`, `users`, `memberships`, `user_sessions` |
| Cadastros | `sites`, `agents`, `cameras`, `zones`, `event_rules` |
| Segurança | `occurrences`, `occurrence_updates` |
| Operação | `zone_metrics_1m` |
| Auditoria | `audit_logs` |
| Protocolo | `ingested_messages` (idempotência) |

- Toda tabela de dados de cliente tem `organization_id` e **Row-Level
  Security** (`ENABLE` + `FORCE`, valendo também para o dono das tabelas): a
  política `tenant_isolation` só mostra e só aceita linhas da organização em
  `app.current_org`. Sem organização definida, nada aparece. A aplicação define
  a organização por transação (`set_config(..., true)`), reaplicada a cada
  transação da sessão; nunca vaza para o próximo uso da conexão.
- Exceção controlada: a política `agent_lookup` deixa *ler* um agente quando
  `app.agent_lookup` é igual ao hash do token ou do código de ativação. É como
  a API acha o agente antes de saber a organização.
- Tabelas de identidade (`organizations`, `users`, `memberships`,
  `user_sessions`) e `ingested_messages` não têm RLS; o acesso é controlado pela
  aplicação.
- Índices compostos seguindo as consultas: `(organization_id, started_at DESC)`,
  `(organization_id, camera_id, started_at DESC)`, `(organization_id, bucket_start)`.
- `occurrences` registra `rule_version` e `zone_version` vigentes.
- `agents.last_seen_at` / `agents.version` substituem uma tabela de heartbeats.
- Previstas para fases seguintes: `agent_commands`, `event_feedback`,
  `notifications`, `event_evidence`, `camera_metrics_1m`.

## 6a. Acesso ao painel

- Senhas com Argon2id (mínimo 10 caracteres). Cinco erros seguidos bloqueiam a
  conta por 15 minutos. E-mail inexistente e senha errada têm a mesma resposta.
- Sessão em cookie `HttpOnly`, `SameSite=Lax`, `Secure` (padrão), válida por
  12 h; o banco guarda só o SHA-256 do token e o logout apaga a sessão.
- CSRF: toda alteração exige o cabeçalho `X-Alessio-Client`, que outro site só
  conseguiria enviar passando por um preflight CORS que recusamos.
- Papéis: `viewer` (consulta), `operator` (+ reconhecer ocorrências), `admin`
  (+ agentes, locais, membros, auditoria), `owner` (+ gerenciar proprietários).
  A organização precisa manter pelo menos um proprietário.
- Organizações novas e o primeiro proprietário: `python -m alessio_api.admin
  create-organization`. Demais pessoas entram por convite (link de uso único,
  72 h; o token vai no fragmento `#` da URL para não aparecer em logs).
- `audit_logs` registra criação/ativação/revogação de agentes, mudanças de
  membros e reconhecimento de ocorrências.

## 6b. Regras de negócio

### R1. Infraestrutura própria ou em comodato

- A infraestrutura de um cliente (câmeras, computador do agente, gravador,
  switch, nobreak) pode ser **do cliente** ou **da Alessio em comodato**. A
  propriedade é por equipamento: um mesmo cliente pode ter os dois tipos.
- Equipamento em comodato pertence sempre a um **contrato de comodato** ativo
  do mesmo cliente e pode ter **valor mensal** (soma na mensalidade) e **valor
  de reposição**. Equipamento do cliente não tem contrato nem valor mensal. O
  banco garante isso (restrição `equipment_ownership_contract`).
- **Só a equipe Alessio cadastra e altera** equipamentos e contratos (área
  Plataforma; acesso dado com `python -m alessio_api.admin grant-staff`). O
  administrador do cliente só consulta (tela Equipamentos).
- Encerrar um contrato não apaga nada: os itens que ainda estão no cliente
  aparecem como "a devolver" até a devolução ser registrada. Contrato encerrado
  não recebe equipamento novo.
- O resumo considera só o que está no cliente (em uso ou em manutenção).
- Fora por enquanto: manutenção e chamados, anexos (contrato e termo de
  entrega em PDF) e a cobrança em si.

## 7. Plano de fases

| Fase | Escopo | Situação |
| --- | --- | --- |
| 0 | Vídeo de arquivo → agente → ocorrência no PostgreSQL → página web. Pacote `contracts` e protocolo versionado. | **Concluída** |
| 1 | Usuários, organizações, permissões, **Row-Level Security**, cadastro de agentes com token de uso único e credenciais revogáveis; painel com login. | **Concluída** |
| 2 | RTSP em produção (reconexão já existe em forma básica), canal de comandos (snapshot, teste de conexão, recarga de config), recarga de configuração sem reiniciar, replay como ferramenta de backtesting. | |
| 3 | Quatro regras iniciais, entradas/saídas/permanência, modo sombra no painel, versionamento de configuração. | |
| 4 | Editor de zonas sobre snapshot, central de ocorrências com SSE, feedback de falso alarme, relatórios de Operação. | |
| 5 | Piloto: precisão/recall em conjunto rotulado, custo por câmera, isolamento, backup, recuperação. | |

Adiados conscientemente: descoberta ONVIF, blur de rostos, detecção de
sabotagem de câmera, múltiplos backends de inferência, WebSocket/MQTT para
comandos (começar com long-poll).

## 8. Limitações conhecidas

- **Câmeras, zonas e regras** ainda são cadastradas só pelo seed de
  demonstração; o cadastro no painel chega com o editor de zonas (Fase 4) e as
  regras configuráveis (Fase 3). Locais têm API (`POST /api/v1/sites`), sem tela.
- **Um papel de banco só.** A aplicação usa o dono das tabelas, sujeito ao RLS
  por `FORCE`. Em produção, separar um papel de migração (dono) de um papel da
  aplicação sem permissão de DDL.
- **Sem e-mail.** Convites e códigos de ativação são exibidos para quem os
  gera copiar e enviar. Também não há "esqueci minha senha" ainda: um
  administrador remove e convida a pessoa de novo.
- **Bloqueio de login por conta**, não por IP; um limite por IP (no proxy ou
  na API) fica para antes da exposição pública.
- **Detector HOG** tem baixa precisão (subconta pessoas e gera falsos
  positivos). Serve para provar o fluxo, não para avaliar o produto.
- O agente lê a configuração apenas ao iniciar.
- Painel atualiza por polling a cada 5 s (SSE na Fase 4).
- `ingested_messages` cresce indefinidamente; precisa de rotina de retenção.
