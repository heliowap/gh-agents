FROM ubuntu:24.04

# gh-agents job image. Each tool names its consumer:
#   git, gh, jq, curl, ca-certificates — the bash steps (gh api, dedup, checkout deps)
#   python3 — scripts/review_blocking.py
#   node22 — JS actions inside the container (FORCE_JAVASCRIPT_ACTIONS_TO_NODE24)
#   opencode — the ci-doctor job invokes `opencode run` directly
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git jq python3 xz-utils \
 && rm -rf /var/lib/apt/lists/*

# gh CLI — official apt repo
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update && apt-get install -y --no-install-recommends gh \
 && rm -rf /var/lib/apt/lists/*

# Node 22 — official tarball (no nodesource)
ARG NODE_VERSION=22.23.3
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    | tar -xJ -C /usr/local --strip-components=1

# opencode CLI — pinned: a floating latest makes the image non-reproducible.
# Bump deliberately alongside runtime/VERSION.
ARG OPENCODE_VERSION=1.18.32
RUN curl -fsSL https://opencode.ai/install | bash -s -- --version "$OPENCODE_VERSION" \
 && ln -s "$HOME/.opencode/bin/opencode" /usr/local/bin/opencode

CMD ["bash"]
