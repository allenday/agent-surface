BASE_URL=https://raw.githubusercontent.com/allenday/agent-surface/main/src/agent_surface/skills

mkdir -p ~/.codex/skills/agent-friendly-cli-design
curl -fsSL $BASE_URL/agent-friendly-cli-design/SKILL.md -o ~/.codex/skills/agent-friendly-cli-design/SKILL.md
curl -fsSL $BASE_URL/agent-friendly-cli-design/reference.md -o ~/.codex/skills/agent-friendly-cli-design/reference.md

mkdir -p ~/.codex/skills/agent-surface-authoring
curl -fsSL $BASE_URL/agent-surface-authoring/SKILL.md -o ~/.codex/skills/agent-surface-authoring/SKILL.md
curl -fsSL $BASE_URL/agent-surface-authoring/reference.md -o ~/.codex/skills/agent-surface-authoring/reference.md
