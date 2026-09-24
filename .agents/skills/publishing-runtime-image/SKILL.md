---
name: publishing-runtime-image
description: Use when changing runtime/Dockerfile, adding tools to the job container image, or publishing a new ghcr.io/heliowap/gh-agents-runtime tag.
---

# Publishing the runtime image

## Overview

Agent jobs run inside `ghcr.io/heliowap/gh-agents-runtime:<tag>` — our own
image (ubuntu24 + node22 + git + gh + python3 + curl). Callers can opt out
with `use_container: false`, but the default is container isolation. Rules:
`docs/conventions/fleet.md` ("Runtime image").

## Authoring rules

- Base image pinned at least to a major tag (`FROM ubuntu:24.04`), never a
  floating `latest`.
- Each installed tool gets a line saying who needs it — node for the actions
  runtime, `gh` for API calls, etc. If you can't name the consumer, don't
  install it.
- No credentials, no `GITHUB_TOKEN`, no user home baked in.

## Build and push

```bash
TAG=v<N>   # bump on ANY tool change — adding a tool bumps the tag
docker build -t ghcr.io/heliowap/gh-agents-runtime:$TAG runtime/
gh auth token | docker login ghcr.io -u <user> --password-stdin
docker push ghcr.io/heliowap/gh-agents-runtime:$TAG
```

- Workflows reference a tag, never `latest`. Update the `container:` line in
  `agents.yml` in the same change that needs the new image.
- `build-runtime.yml` (`.github/workflows/`) automates build+push — prefer
  it over manual pushes once it exists; manual push is the bootstrap path.

## Verify

A real job ran on the new tag — link the run. `docker build` succeeding
locally is not done. See verifying-changes.

## Common mistakes

- Pushing without bumping the tag — the running fleet keeps the old image
  under the same name and nothing is reproducible.
- Installing a repo-specific tool — the image holds only what the agents
  need; repo tools belong in the caller's own setup steps.
- Baking any token or key into a layer — check `docker history` if unsure.
