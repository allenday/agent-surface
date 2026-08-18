# Agent-Friendly CLI Contract Reference

## Contents

- Success envelope
- Error envelope
- Bounded high-branch-factor actions
- Optional resolution metadata
- YAML presentation styles

## Success Envelope

```yaml
schema_version: "1"
ok: true
command:
  raw: [repo, inspect, "my repo", --details]
  parsed:
    path: [repo, inspect]
    args:
      repo: "my repo"
    options: {}
    flags: [details]
result:
  repo: "my repo"
  status: clean
next_actions:
  items:
    - rel: summarize
      command: [repo, inspect, "my repo", --summary]
      description: Show a compact repository summary
  total: 1
  returned: 1
  truncated: false
```

## Error Envelope

```yaml
schema_version: "1"
ok: false
command:
  raw: [repo, inspect, "my repo", --details, unexpected]
  parsed:
    path: [repo, inspect]
    args:
      repo: "my repo"
      unexpected: unexpected
    options: {}
    flags: [details]
error:
  code: unexpected_argument
  message: Unexpected argument after repository name
  details:
    - path: [command, parsed, args, unexpected]
      value: unexpected
fix: Remove the extra argument or inspect command help.
next_actions:
  items:
    - rel: help
      command: [repo, inspect, --help]
      description: Show supported arguments and flags
  total: 1
  returned: 1
  truncated: false
```

## Bounded High-Branch-Factor Actions

Return a relevant sample and a discovery command rather than every reachable action:

```yaml
next_actions:
  items:
    - rel: inspect-child
      command: [repo, inspect, src]
      description: Inspect the most relevant child
  total: 180
  returned: 1
  truncated: true
  discover:
    command: [repo, actions, list, --for, "state_7c91", --limit, "20"]
    description: List additional available actions
```

For repeated action shapes, expose one template and a bounded parameter source:

```yaml
next_actions:
  items:
    - rel: inspect-child
      command_template: [repo, inspect, "{child}"]
      parameters:
        child:
          type: string
          source:
            command: [repo, children, list, --cursor, abc123]
      description: Inspect one child
  total: 1
  returned: 1
  truncated: false
```

## Optional Resolution Metadata

```yaml
command:
  raw: [repo, inspect, "my repo", --details]
  parsed:
    path: [repo, inspect]
    args:
      repo: "my repo"
    options: {}
    flags: [details]
  resolved:
    executable: /Users/example/.local/bin/repo
    version: 1.4.2
    cwd: /Users/example/src/project
    config: /Users/example/.config/repo/config.yaml
```

## YAML Presentation Styles

Block and flow YAML are equivalent presentations of the same contract. A CLI may expose both without changing field semantics:

```yaml
{schema_version: "1", ok: true, result: {status: clean}, next_actions: {items: [], total: 0, returned: 0, truncated: false}}
```
