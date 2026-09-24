# Docs prose (README, specs, comments)

- Plain, short, declarative sentences for a repo owner deciding whether to
  trust this. Lead with the point.
- Exact about limits and the unverified: "verified on repo-level runners,
  org-level pending" is a sentence worth keeping; rounding a caveat away is a
  bug. `NÃO VERIFICADO` in the text beats a confident guess.
- Tables for symptom/cause/fix and option/meaning shapes. Commands in fenced
  `bash` blocks, runnable as written. Identifiers, flags, paths and variable
  names in backticks.
- No emoji, no marketing adjectives, no "simply"/"just". Sentence-case
  headings. Prose wraps near 100 columns; tables and URLs may run long.
- Português e inglês valem; siga a consistência local do arquivo tocado.
  Specs de design podem ser em português; mensagens voltadas a usuários de
  CI (comentários que os agents postam) seguem o idioma do repo alvo.
