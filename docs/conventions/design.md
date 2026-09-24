# Design: deep modules

The central concept is the **deep module** (Ousterhout, *A Philosophy of
Software Design*): a lot of behaviour behind a small interface. The
`codebase-design` skill is the shared vocabulary — module, interface,
implementation, depth, seam, adapter, leverage, locality. Load it when
designing or improving a module's interface, deciding where a seam goes, or
when an interface's shape is itself the question. Use its terms exactly.

How it applies here:

- **Every artifact type has an interface.** A script's interface is its CLI
  (flags, env, exit codes). A workflow job's interface is its `with:` inputs.
  An agent's interface is its `opencode.json` entry plus the output contract
  in its prompt. Depth is measured the same way for all of them: how much a
  caller gets per unit of interface it must learn.
- **Small interface, deep implementation.** `review-blocking` should be
  "comments in → verdict out", not a tour of jq and pagination. A fleet
  script should be `enable-repo.sh owner/repo` — the token dance, config.sh
  flags and svc.sh details are implementation.
- **The deletion test.** Imagining deleting the module: if the complexity
  vanishes, it was a pass-through (shallow — merge it into its caller). If it
  reappears across N callers, the module was earning its keep.
- **One adapter means a hypothetical seam.** Don't add a seam for a single
  backend "in case depot changes" — two real adapters make a seam real.
- **Flag fatigue is the smell.** A script whose flags outnumber its verbs, or
  a workflow input list callers must fully specify to get default behaviour,
  is an interface wider than the implementation behind it.

Interface changes are the expensive kind of change — callers outside this
repo depend on them. A change to `agents.yml` inputs is a breaking change
(see `commits.md`), which is why depth pays double here: every input you
don't add is a contract you don't maintain.
