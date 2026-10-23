# Design system Alessio Vision

Fonte única de tokens: `tokens.json`. Depois de editar, rode `npm run tokens` (gera `src/design-system/tokens.css`; o build falha se ele estiver desatualizado). Componentes em `src/ui/`; logos em `public/brand/` (gerados do original em `source/` por `scripts/build_logo_assets.py`); fontes em `fonts/` (OFL). `npm run ds:bundle -- <pasta>` empacota os componentes para a referência navegável.

Alessio Vision é uma plataforma de visão computacional para segurança e operação: um agente analisa câmeras e o painel mostra ocorrências, a saúde das câmeras e indicadores. A interface é uma ferramenta de trabalho para operadores e gestores. Ela precisa ser lida de relance, inclusive à noite, e deixar claro o que exige atenção agora.

## Princípios

- **Estado antes de decoração.** Tudo que pede ação aparece por cor *e* por texto: um selo `Em andamento` em `status-danger-*`, nunca só um ponto vermelho.
- **Dados com cara de dados.** Horários, contagens e IDs usam `text-data` (IBM Plex Mono, algarismos tabulares) e alinham em coluna.
- **Bordas, não sombras.** Painéis e cartões são separados por `border` sobre `surface`. `shadow-raised` só existe para o que flutua (menus, diálogos).
- **Os dois temas são primeira classe.** Centrais de monitoramento operam no escuro: todo par de texto e fundo foi verificado nos temas claro e escuro.

## Conteúdo e voz

- Português do Brasil, frases curtas e diretas, voz ativa. Fale do que a pessoa reconhece (câmera, ocorrência, zona), não de como o sistema funciona por dentro (heartbeat, outbox, payload).
- Rótulos de estado são substantivos ou particípios curtos com inicial maiúscula: `Analisando`, `Sem sinal`, `Agente sem contato`, `Em andamento`, `Encerrada`.
- Botões dizem exatamente o que acontece: `Reconhecer ocorrência`, `Testar conexão`, `Salvar zona`. Evite `OK`, `Enviar`, `Clique aqui`.
- Erros explicam o problema e como resolver, sem desculpas: `Não foi possível conectar à câmera. Confira o endereço RTSP no agente e tente de novo.`
- Datas e horas no formato brasileiro, relógio de 24 horas, fuso do local monitorado: `24/10/2026, 23:00:02`. Durações por extenso curto: `1 min 19 s`, `2 h 5 min`.
- Números com vírgula decimal (`0,35`) e unidades com espaço (`10 s`, `5 fps`).
- Sem emoji, em lugar nenhum da interface.
- Monitoramento de pessoas é um tema sensível (LGPD): descreva o que o sistema detecta ("pessoa na zona"), nunca quem é a pessoa.

## Cor

- Fundo da página `bg`; painéis, cartões, tabelas e campos em `surface`; cabeçalho de tabela em `surface-sunken`.
- Texto principal `ink`; secundário (metadados, rótulos, dicas) `ink-muted`. Ambos passam de 4,5:1 sobre `bg`, `surface` e `surface-sunken` nos dois temas.
- `accent` é o azul da marca na interface: ação principal, links e foco de seleção. Texto sobre ele usa `on-accent`, que é branco no claro e escuro no tema escuro, porque o azul é clareado lá.
- `accent-soft` marca linha em hover ou selecionada; o texto sobre ele é `ink`.
- Estados usam pares fixos fundo/texto: `status-ok-*` (normal, `Analisando`), `status-warn-*` (verificar, `Sem sinal`), `status-danger-*` (ação imediata, `Em andamento`, erro), `status-neutral-*` (sem urgência, `Encerrada`). Nunca use a cor de status como decoração.
- `brand-blue` e `brand-navy` são as cores do logo. Use-as em peças de marca; na interface use os tokens semânticos.
- Anel de foco: 2px sólido em `focus-ring`, afastado 2px do elemento.
- Bordas: `border` para contornos e divisórias; `border-strong` para campos e botões secundários (3:1 nos dois temas).

## Tipografia

- Títulos em Sora (`--font-display`): `text-display` uma vez por tela, `text-title` para seções, `text-heading` para nomes de câmera e títulos de painel.
- Texto em IBM Plex Sans (`--font-sans`): `text-body` para texto corrido e células, `text-body-strong` para ênfase, `text-small` para metadados, `text-label` (maiúsculas, espaçamento 0,06em) para cabeçalhos de coluna.
- Dados em IBM Plex Mono (`--font-mono`): `text-data` para horários, durações, contagens e IDs.
- As fontes são servidas pelo próprio painel (arquivos em `fonts/`, licença OFL), sem Google Fonts, para não enviar o IP de quem usa o painel a terceiros.

## Espaço, cantos e layout

- Escala de 4px: `space-1` (4) a `space-7` (48). Padding de painel `space-4`; células `space-3`/`space-4`; entre painéis `space-5`; entre seções `space-6`.
- Margem lateral mínima de `space-4` (16px) em qualquer largura; no celular, tabelas rolam dentro do painel, nunca a página.
- Cantos: `radius-sm` em campos, `radius-md` em botões, painéis e cartões (ecoa o hexágono do símbolo), `radius-lg` em diálogos, `radius-pill` em selos.
- Largura máxima do conteúdo 1160px.

## Movimento

- Transições de 120ms só em cor de fundo e borda (hover). Nada pisca nem pulsa para chamar atenção: um selo `status-danger` já faz isso. Com `prefers-reduced-motion`, sem transições.

## Logo

- Use os arquivos do grupo **Logos**, nunca redesenhe nem recolora. Fundo claro: as versões sem sufixo; fundo escuro: `-on-dark`, em que o navy vira claro e o azul é clareado.
- `alessio-vision-horizontal` no cabeçalho da aplicação, com 36px de altura (mínimo 28px).
- `alessio-vision-mark` (símbolo) em espaços quadrados: ícone do app, favicon, avatar do sistema em notificações. Mínimo 20px.
- `alessio-vision-logo` (empilhado, com "Sistemas inteligentes") em capas, login e materiais impressos. Mínimo 120px de largura.
- Área de proteção ao redor de qualquer versão: um quarto da altura do símbolo.
- Não aplique sombra, contorno, gradiente ou rotação; não coloque sobre fotos sem um painel `surface` por trás.

## Iconografia

- Ainda não há um conjunto de ícones da marca. Os selos de status usam um ponto em `currentColor` e o texto carrega o significado.
- Quando ícones forem necessários (Fase 4), escolher um conjunto de traço único e 1,5–2px, em `ink` ou `ink-muted`, sempre acompanhado de texto em ações.

## Componentes

`AppHeader`, `Badge`, `Button`, `DataTable`, `Logo`, `Panel` e `TextField`, publicados em `window.AlessioUI`. No código, a fonte é `apps/web/src/ui/` do repositório alessiovision; os tokens vêm de `apps/web/design-system/tokens.json` e o CSS é gerado por `npm run tokens`.
