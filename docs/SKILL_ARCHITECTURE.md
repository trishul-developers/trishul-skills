# Cross-Platform AI Agent Skill Architecture

This document provides a comparative architectural breakdown of skill systems across Anthropic Claude Code, OpenAI Codex, and Google Antigravity (AGY).

---

## 1. Skill Concept and Common Anatomy

Across all three ecosystems, a **Skill** is a self-contained unit of specialized procedural knowledge, tooling, and execution protocols that extends an AI agent's baseline capabilities.

A canonical skill bundle consists of:
```
<skill-name>/
  ├── SKILL.md            # Mandatory: Instructions, YAML frontmatter, execution workflows
  ├── scripts/            # Optional: Deterministic helper scripts (Python, PowerShell, Bash)
  ├── references/         # Optional: Detailed API specs, architecture manuals, reference docs
  ├── assets/ / schemas/  # Optional: Templates, input/output JSON schemas, diagrams
  └── agents/             # Optional: Subagent system prompts and role definitions
```

### Universal Frontmatter Specification
```yaml
---
name: <kebab-case-identifier>
description: <Clear, concise description explaining when and how to activate this skill>
compatibility: <CLI / platform / runtime dependencies>
tags: [<taxonomy-tags>]
---
```

---

## 2. Platform Comparison Matrix

| Dimension | Anthropic Claude Code | OpenAI Codex | Google Antigravity (AGY) |
|---|---|---|---|
| **Primary Discovery Root** | `~/.claude/skills/`, plugin manifests | `~/.codex/skills/`, plugin cache | `~/.gemini/config/skills/`, builtin skills |
| **Project-Level Root** | `.claude/skills/`, `.agents/skills/` | `.agents/skills/`, `.codex/skills/` | `<repo>/.gemini/skills/`, `.agents/skills/` |
| **Interactive Invocation** | Slash command (e.g. `/skill-name`) or autonomous triggering | Slash command / intent detection | Dynamic tool matching / skill prompt injection |
| **Non-Interactive Headless Mode** | `claude -p "<prompt>"` / `--print` | `codex exec "<prompt>"` | `agy -p="<prompt>"` / `--print` |
| **Reasoning Effort Tuning** | Built into model tiers (Haiku / Sonnet / Opus) | `--config model_reasoning_effort="<low\|medium\|high\|ultra>"` | `--effort <low\|medium\|high\|xhigh\|max>` |
| **Sandboxing & Permissions** | `--allowed-tools`, `--dangerously-skip-permissions` | `-s <read-only\|workspace-write\|danger-full-access>` | `--mode <auto\|accept-edits\|plan>`, `--dangerously-skip-permissions` |
| **Output Contracts** | `--output-format <text\|json\|stream-json>`, `--json-schema` | `--output-schema <file>`, `--json`, `-o <file>` | `--output-format <text\|json>`, `--json-schema` |
| **Session Continuity** | `--resume <session-id>`, `--continue` | `codex exec resume <thread-id>`, `--fork` | `--conversation <id>`, `--continue` |

---

## 3. Sandboxing & Safety Models

### OpenAI Codex
Codex enforces OS-level process sandboxing:
- **`read-only`**: The agent can inspect file trees, read source files, and query symbols, but cannot modify files or execute mutating commands.
- **`workspace-write`**: Writes are strictly confined to the project root and explicitly whitelisted directories (`--add-dir`).
- **`danger-full-access`**: Unrestricted shell access; requires explicit bypass flags.

### Google Antigravity
Antigravity manages execution modes:
- **`plan`**: Read-only exploration and multi-step plan authoring without file modification tools.
- **`auto`**: Standard execution where file edits require approval unless `--dangerously-skip-permissions` is set.
- **`accept-edits`**: Directly applies diff proposals into the workspace.

### Claude Code
Claude Code employs tool-level authorization:
- **Allowed Tools Whitelist**: Constraints like `--allowed-tools "Read,Edit,Bash(git *)"` permit deterministic subsets of tools.
- **`--bare` Execution**: Minimal footprint skipping hook scripts, LSP indexing, and auto-memory for predictable batch runs.

---

## 4. Cross-Provider Skill Interoperability

Because each CLI exposes slightly different flags and stdin requirements, this repository introduces three universal headless runners in `skills/headless/`:
1. `codex-headless`: Wraps `codex exec`.
2. `agy-headless`: Wraps `agy -p`.
3. `claude-headless`: Wraps `claude -p`.

These runners normalize inputs, manage process lifecycles, handle Windows-specific limits, and output uniform `result.json` audit files.
