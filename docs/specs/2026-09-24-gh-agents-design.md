# gh-agents — design

Serviço de agentes de código (OpenCode) acionados por GitHub Actions, rodando
grátis numa fleet self-hosted na VPS `intrador-tech-vps`, habilitável em
qualquer repo (pessoal, org `intrador`, org `All-Medical`, terceiros com admin)
via um reusable workflow central.

Data: 2026-09-24. Status: aprovado em conversa; aguardando revisão escrita.

## Contexto

- `heliowap/intrador-platform` já tem `opencode.yml` (review automático em
  PR→dev + fix via `/oc`), agents `reviewer`/`fixer` em `opencode.json`, skills
  em `.agents/skills/`. Tudo roda em `ubicloud-standard-2` (pago).
- Existem 8 runners `factory-ci-*` registrados no repo, processos vivos desde
  2026-09-03 **sem unit files** — não sobrevivem a reboot. Serão
  descomissionados (não reaproveitados).
- Setup anterior (`factory-review`: webhook :8788 + runners codex) foi
  desmontado; este design usa triggers nativos do Actions.

## Decisões tomadas

| Pergunta | Decisão |
|---|---|
| Escopo de repos | qualquer repo habilitado sob demanda |
| O que migra p/ self-hosted | jobs de agente; CI normal via switch `vars.CI_RUNNER` |
| CI-fix | híbrido: diagnóstico automático, correção só via `/oc` |
| Repo central | `heliowap/gh-agents` **público** (necessário p/ cross-owner) |
| Fleet | nova, usuário dedicado; `factory-ci` descomissionado |
| Repos pessoais | ficam em `heliowap` (repo-runners); orgs usam org-runners |
| Repos p/ self-hosted | só privados |
| Gate de comentário | `author_association` ∈ {OWNER, MEMBER, COLLABORATOR}, não-Bot |
| Modelo | `opencode-go/glm-5.3-flash` (ZDR), igual ao atual |

## Arquitetura

```
heliowap/gh-agents (público)
├── .github/workflows/
│   ├── agents.yml            reusable workflow (workflow_call): review/fix/ci-doctor
│   └── build-runtime.yml     build+push da imagem de runtime p/ ghcr.io
├── agents/opencode.json      agents default: reviewer, fixer, ci-doctor
├── skills/                   skills genéricas (fallback p/ repos sem .agents/skills)
├── runner/                   fleet: enable-repo.sh, enable-org.sh, disable-*.sh, status.sh
├── runtime/Dockerfile        imagem dos jobs (ubuntu24 + node22 + gh + git + python3)
└── docs/specs/               este doc + 2026-09-24-vps-dashboard-design.md

<repo-alvo>/.github/workflows/agents.yml   caller ~20 linhas:
  on: pull_request, issue_comment, pull_request_review_comment, workflow_run
  jobs: agents: uses: heliowap/gh-agents/.github/workflows/agents.yml@v1
        secrets: inherit
```

Resolução de agents/skills: o checkout do repo alvo é a fonte primária
(`opencode.json`, `.agents/skills/`). Se ausentes, um step copia os defaults
do checkout do `gh-agents`. Repo mantém autonomia; repo sem nada funciona.

## Jobs do reusable workflow

`runs-on: ${{ vars.AGENT_RUNNER || inputs.runs-on }}` em todos os jobs;
input `runs-on` default `'self-hosted'`. `vars` resolve no contexto do repo
chamador — **verificar na implementação**; fallback documentado: caller passa
`with: { runs-on: ... }` explicitamente.

### `review`
- Trigger (no caller): `pull_request` opened/synchronize/reopened/
  ready_for_review, não-draft; paths-ignore `docs/**`, `**/*.md`.
- Agent `reviewer`: read-only (edit/webfetch/websearch deny; bash só git/gh
  read). Saída: BLOCKING/WARNING/NIT, `path:linha`, `SUMMARY: N/N/N`.
- Pós-step: BLOCKING → issue `review-blocking` (uma por PR, reabre se fechada).
  Adaptação genérica de `scripts/review_blocking.py` do intrador-platform,
  versionada no gh-agents.
- `permissions: contents:read, pull-requests:write, issues:write`.
- Timeout 20min. Concurrency por `event_name + PR/issue` (comentário não
  cancela review — bug #1417 do intrador).

### `fix` (`/oc`, `/opencode`)
- Trigger: `issue_comment`/`pull_request_review_comment` `created`, body
  contém `/oc` ou `/opencode`, autor OWNER/MEMBER/COLLABORATOR, não-Bot.
- Agent `fixer`: bash liberado, edit liberado; webfetch/websearch deny.
  Em PR: commita na branch do PR. Em issue: branch nova + PR.
- `permissions: contents:write, pull-requests:write, issues:write`.
- Timeout 30min.

### `ci-doctor`
- Trigger: `workflow_run` `completed` + `conclusion == 'failure'`; input
  `ci_workflows` (nomes a observar, default: todos).
- Agent `ci-doctor`: baixa `gh run view --log-failed`, diagnostica, comenta
  no PR associado ao run (sem PR associado → comenta no run via issue? não:
  **pula silenciosamente** e loga). Só diagnóstico — correção via `/oc`.
- Input `ci_auto_fix: false` reservado p/ v2.
- `permissions: actions:read, contents:read, pull-requests:write, issues:write`.
- Dedup: um comentário de diagnóstico por (workflow, sha) — marca via
  `<!-- ci-doctor:sha -->` no comentário.

### Comum
- Action: `anomalyco/opencode/github` **pinada por tag** (`@vX`), não `@latest`.
- `use_github_token: true`, `share: false`, `model:` input
  (default `opencode-go/glm-5.3-flash`).
- Env `OPENCODE_API_KEY` de `secrets: inherit` do caller.
- Jobs rodam em `container: ghcr.io/heliowap/gh-agents-runtime:vX` (imagem
  própria: ubuntu24 + node22 + git + gh + python3). Input
  `use_container: true` default; repos cujos testes precisam de Docker setam
  `false` (roda no host, menos isolamento — documentado).

## Runner switch

- **Agentes**: `runs-on` via `vars.AGENT_RUNNER` (por repo) →
  `inputs.runs-on` (default central no gh-agents). Fleet-wide = 1 edit no
  gh-agents; por-repo = `gh variable set AGENT_RUNNER`.
- **CI normal**: uma conversão por workflow: `runs-on:
  ${{ vars.CI_RUNNER || 'ubuntu-latest' }}`. Depois disso, backend vira
  variável de repo — o dashboard (spec B) opera isso via API de variables.
- Valores válidos documentados: `self-hosted`, `ubuntu-latest`,
  `depot-ubuntu-24.04[-4|-8]`, `ubicloud-standard-2`.

## Fleet

- Usuário dedicado `gh-agents` (system user, membro de `docker`).
  Runners em `/home/gh-agents/runners/<escopo>/<n>/`, escopo =
  `org--<org>` ou `<owner>--<repo>`. Checkout do gh-agents em
  `/home/gh-agents/gh-agents` (scripts rodam dali).
- `runner/enable-repo.sh <owner>/<repo> [N=2]`: `gh api
  repos/{o}/{r}/actions/runners/registration-token` → `config.sh --unattended
  --labels agents` → `svc.sh install` (como gh-agents) + `start`.
- `runner/enable-org.sh <org> [N=2]`: idem com
  `orgs/{org}/actions/runners/registration-token` (PAT `admin:org`).
- `disable-repo.sh` / `disable-org.sh`: `config.sh remove --token` +
  `svc.sh uninstall` + remove dir. `status.sh`: units + runners via API.
- Labels: `agents` (+ self-hosted/linux/x64 default). Repo-level runner só
  enxerga o próprio repo; `self-hosted` já é filtro suficiente.
- Sizing: N=2 por escopo (4 vCPUs; jobs são I/O-bound em API de LLM).
- Higiene: timer systemd `gh-agents-cleanup.timer` diário — apaga `_work` de
  runners há >7 dias parados. (Sucessor do factory-disk-cleanup.)
- Descomissionamento `factory-ci`: parar processos, `config.sh remove`
  (desregistra no GitHub), remover `/home/helio/actions-runner/`, encostar
  `remove-factory-review.sh` junto.

## Segurança

- Self-hosted **somente em repo privado** — `enable-*.sh` verifica
  `visibility` antes de registrar e aborta se público.
- Gate de autor em comentários (acima). Bot não dispara bot.
- `gh-agents` público: branch protection em `main` + callers pinados em tag
  (`@v1`) — defesa contra adulteração do reusable workflow.
- Jobs em container por default; `gh-agents` user sem acesso a chaves de
  outros usuários (`vpsdash`, `helio`).
- PAT de registro só no shell local; nunca em workflow/secret do gh-agents.
- `permissions` mínimas por job (acima). Nenhum job tem `actions:write`.

## Segredos e credenciais

| Segredo | Onde | Uso |
|---|---|---|
| `OPENCODE_API_KEY` | secret de cada repo habilitado | auth da action |
| `GITHUB_TOKEN` | automático | git ops, comentários, issues |
| PAT local | shell do operador | `enable-*.sh`, descomissionamento |
| GitHub App "gh-agents-ops" | spec B | dashboard: variables API, runners API |

## Onboarding de um repo (checklist)

1. `enable-repo.sh owner/repo 2` (ou repo já coberto por org-runner).
2. `gh secret set OPENCODE_API_KEY --repo owner/repo`.
3. Copiar caller template p/ `.github/workflows/agents.yml` (ajustar
   `on.pull_request.branches` p/ a default do repo).
4. Opcional: `vars.AGENT_RUNNER`, `vars.CI_RUNNER`, `opencode.json` próprio.
5. Opcional: instalar GitHub App gh-agents-ops (spec B) p/ switch via UI.

## Rollout e verificação

1. Criar repo `gh-agents` (público), workflow, imagem, scripts, tag `v1`.
2. Descomissionar `factory-ci-*`; instalar fleet nova.
3. Habilitar `heliowap/intrador-platform` (repo-runners; já tem secrets e
   skills — dogfood completo). `opencode.yml` local pode coexistir na
   transição; depois é substituído pelo caller.
4. Verificar end-to-end: PR de teste → review no runner local; `/oc` →
   commit; CI quebrado → comentário de diagnóstico; `vars.AGENT_RUNNER`
   trocado → job vai para outro backend.
5. Habilitar orgs (`intrador`, `All-Medical`) e demais repos sob demanda.

## Fora de escopo / v2

- `ci_auto_fix` (auto-correção de CI sem comando).
- Runners efêmeros / autoscaling (ARC).
- Dashboard/UI (spec B) — o switch aqui é por API/CLI; UI vem depois.
- Windows runners.
- Review obrigatório como merge gate (decisão de produto por repo).
