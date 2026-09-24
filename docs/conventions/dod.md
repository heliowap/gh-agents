# Definition of done and feedback loops

## DoD per change type

| Change | Green means | Evidence |
|---|---|---|
| `docs/**` only | prose rules (`prose.md`), claims verified or marked | the rendered text |
| `runner/*.sh` | `shellcheck` clean; ran twice, converged; verification block output | terminal output in PR or linked run |
| `.github/workflows/` | `actionlint` clean **and** exercised on a real caller repo | link to the run; if not exercised, the PR says so plainly |
| `agents/`, `skills/` | schema valid; behaviour evidence — run log showing the old failure and the new output | before/after log |
| `runtime/` | image builds, tag bumped, a job ran on it | run link |
| code (py/go) | `tdd` loop followed; tests at agreed seams; complexity budget (`testing.md`) | red→green history or the failing-without-fix test |
| dashboard UI | TestSprite test(s) for the touched flow run to a verdict; failure artifacts inspected | run link or dashboard URL; "unverified" if no credentials |

Um item de DoD que se aplica ao diff e **não pôde rodar é falha, nunca
skip** — ferramenta ausente conta como reprovação, não como isenção. Diga o
que falta em vez de declarar pronto.

## Feedback loops: como um agente recebe correção

Do mais barato ao mais caro — escale só quando o anterior não resolve:

1. **Loop local** — `actionlint`, `shellcheck`, schema check, teste focado.
   Re-rodar até verde. Saída vermelha não se interpreta, se corrige ou se
   escala.
2. **TestSprite verify** — mudança de UI: o teste que cobre o fluxo roda até
   veredito (`test run <id> --local <port>`) e artifacts de falha são
   inspecionados. Sem credencial ou sem teste que cubra = "unverified",
   declarado assim no PR.
3. **CI do próprio repo** — o gh-agents dogfood: PRs deste repo passam pelo
   próprio `agents.yml`. O review do agente é feedback estruturado —
   BLOCKING/WARNING/NIT + `SUMMARY` — parseável pelo próximo agente que
   atender o `/oc`.
4. **`/oc` dirigido** — comentário do humano apontando a correção vira o
   prompt do fixer. O formato existe para isso: achado com `path:linha` é
   uma instrução, não uma opinião.
5. **Spec/plan review** — para mudança grande, a correção acontece no papel
   (`docs/specs/`, plano) antes de virar código.

Regras dos loops: bot não dispara bot (o review não chama o fixer sozinho);
uma correção que criou vermelho novo volta ao loop 1; um loop que falhou
duas vezes com a mesma hipótese sobe um nível — o problema provavelmente
está na hipótese, não na execução.
