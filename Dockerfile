FROM node:20-slim

ARG CLAUDE_CODE_VERSION=latest

RUN apt-get update && apt-get install -y --no-install-recommends \
  git \
  curl \
  less \
  procps \
  jq \
  ripgrep \
  ca-certificates \
  python3 \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

USER node

ENV NPM_CONFIG_PREFIX=/home/node/.npm-global
ENV PATH=$PATH:/home/node/.npm-global/bin

RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

WORKDIR /workspace

ENTRYPOINT ["claude", "--dangerously-skip-permissions"]
