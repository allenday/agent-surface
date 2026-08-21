#!/bin/sh
set -eu

BASE_URL=https://raw.githubusercontent.com/allenday/agent-surface/main/src/agent_surface/skills
SKILLS_DIR="${CODEX_HOME:-$HOME/.codex}/skills"

mkdir -p "$SKILLS_DIR/agent-friendly-cli-design"
curl -fsSL "$BASE_URL/agent-friendly-cli-design/SKILL.md" -o "$SKILLS_DIR/agent-friendly-cli-design/SKILL.md"
curl -fsSL "$BASE_URL/agent-friendly-cli-design/reference.md" -o "$SKILLS_DIR/agent-friendly-cli-design/reference.md"

mkdir -p "$SKILLS_DIR/agent-surface-authoring"
curl -fsSL "$BASE_URL/agent-surface-authoring/SKILL.md" -o "$SKILLS_DIR/agent-surface-authoring/SKILL.md"
curl -fsSL "$BASE_URL/agent-surface-authoring/reference.md" -o "$SKILLS_DIR/agent-surface-authoring/reference.md"
