# Skills and Hooks Setup Guide

This guide explains how to set up the g-* skills and UserPromptSubmit hook system for Claude Code and Codex in any repository.

## Overview

The system consists of:
1. **Claude Code Skills** (`~/.claude/skills/`) - Instructions for Claude Code workflows
2. **UserPromptSubmit Hook** (`.claude/hooks/`) - Forces skill evaluation on every prompt
3. **Codex Skills/Protocols** (`~/.codex/skills/`) - Instructions for Codex workflows
4. **Gemini MCP Server** (`~/.codex/mcp/`) - Second opinion via Gemini API
5. **Configuration Files** - Settings for hooks and MCP servers

## Directory Structure

```
~/.claude/
├── settings.json                    # Hooks configuration
└── skills/
    ├── g-planning/
    │   └── skill.md                 # Planning workflow skill
    ├── g-coding/
    │   └── skill.md                 # TDD coding workflow skill
    ├── g-stack/
    │   └── skill.md                 # Git/Graphite stack management
    ├── g-submit/
    │   └── skill.md                 # PR submission workflow
    └── g-service-scaffolder/
        └── skill.md                 # New service scaffolding

~/.codex/
├── config.toml                      # Codex configuration
├── skills/
│   └── PROTOCOL.md                  # Codex workflow protocols
└── mcp/
    ├── .env.mcp                     # Gemini API credentials
    ├── gemini-mcp-server.mjs        # MCP server implementation
    ├── gemini-mcp.sh                # Wrapper script
    └── package.json                 # Dependencies

<your-repo>/
└── .claude/
    └── hooks/
        └── UserPromptSubmit         # Hook script (executable)
```

---

## Step 1: Create UserPromptSubmit Hook

Create the hook script in your repository:

```bash
mkdir -p <your-repo>/.claude/hooks
```

Create `<your-repo>/.claude/hooks/UserPromptSubmit`:

```bash
#!/bin/bash
# UserPromptSubmit hook that forces explicit skill evaluation
#
# This hook requires Claude to explicitly evaluate each available skill
# before proceeding with implementation.

cat <<'EOF'
INSTRUCTION: MANDATORY SKILL ACTIVATION SEQUENCE

Step 1 - EVALUATE (do this in your response):
For each skill in <available_skills>, state: [skill-name] - YES/NO - [reason]

Step 2 - ACTIVATE (do this immediately after Step 1):
IF any skills are YES → Use Skill(skill-name) tool for EACH relevant skill NOW
IF no skills are YES → State "No skills needed" and proceed

Step 3 - IMPLEMENT:
Only after Step 2 is complete, proceed with implementation.

CRITICAL: You MUST call Skill() tool in Step 2. Do NOT skip to implementation.
The evaluation (Step 1) is WORTHLESS unless you ACTIVATE (Step 2) the skills.

Example of correct sequence:
- research: NO - not a research task
- svelte5-runes: YES - need reactive state
- sveltekit-structure: YES - creating routes

[Then IMMEDIATELY use Skill() tool:]
> Skill(svelte5-runes)
> Skill(sveltekit-structure)

[THEN and ONLY THEN start implementation]
EOF
```

Make it executable:
```bash
chmod +x <your-repo>/.claude/hooks/UserPromptSubmit
```

---

## Step 2: Configure Claude Settings

Edit `~/.claude/settings.json` to add the hook:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/your-repo/.claude/hooks/UserPromptSubmit"
          }
        ]
      }
    ]
  }
}
```

---

## Step 3: Create Claude Skills

### g-planning Skill

Create `~/.claude/skills/g-planning/skill.md`:

```markdown
---
name: g-planning
description: Creates comprehensive execution plans by combining Claude Code and Codex analysis, then synthesizing an improved plan from both approaches. Use this when planning complex features or architectural changes. (user)
location: user
---

# g-planning

Creates comprehensive execution plans by combining Claude Code and Codex analysis.

## Process

### Step 1: Claude Code Planning
Read context files:
- `AGENTS.md` (repo root) - Best practices
- `services/<service>/CONTEXT.md` - Service architecture

### Step 2: Codex Planning
Call Codex MCP with context:

```javascript
mcp__codex__codex({
  prompt: `Task: [description]

=== PLANNING INSTRUCTIONS ===
Make a detailed plan. Identify files to change.
Write function names with 1-3 sentence descriptions.
Write test names with 5-10 word descriptions.`,

  "developer-instructions": `=== PROJECT CONTEXT ===
AGENTS.md: [content]
CONTEXT.md: [content]`,

  cwd: "[repo path]",
  "approval-policy": "never",
  sandbox: "read-only"
})
```

### Step 3: Compare & Synthesize
Evaluate both plans, identify gaps, synthesize unified plan.

## Output Format
1. Overview (2-3 sentences)
2. Files to Change
3. Implementation Steps
4. Test Coverage
5. Dependencies
6. Validation
```

### g-coding Skill

Create `~/.claude/skills/g-coding/skill.md`:

```markdown
---
name: g-coding
description: Comprehensive TDD coding workflow with QCHECK via Codex. (user)
location: user
---

# g-coding

TDD coding workflow with automated quality checks.

## TDD Cycle
1. Scaffold stub
2. Write failing test
3. Run test (should fail)
4. Implement
5. Run test (should pass)
6. Lint & typecheck
7. Repeat

## QCHECK via Codex

```javascript
mcp__codex__codex({
  prompt: `You are a SKEPTICAL senior software engineer.

=== CODE TO REVIEW ===
[code]

=== QCHECK INSTRUCTIONS ===
Review against:
1. Writing Functions Best Practices
2. Writing Tests Best Practices
3. Implementation Best Practices`,

  "developer-instructions": `=== PROJECT CONTEXT ===
AGENTS.md: [content]
CONTEXT.md: [content]`,

  cwd: "[repo path]",
  "approval-policy": "never",
  sandbox: "read-only"
})
```

## Quality Gates
✅ All tests pass
✅ Typecheck passes
✅ Linting passes
✅ Build succeeds
✅ QCHECK completed
✅ Issues addressed
```

---

## Step 4: Set Up Gemini MCP Server

### Create Directory
```bash
mkdir -p ~/.codex/mcp
cd ~/.codex/mcp
```

### Create package.json
```json
{
  "name": "gemini-mcp-server",
  "version": "0.1.0",
  "type": "module",
  "bin": {
    "gemini-mcp": "./gemini-mcp-server.mjs"
  },
  "scripts": {
    "dev": "node ./gemini-mcp-server.mjs",
    "inspect": "npx @modelcontextprotocol/inspector node ./gemini-mcp-server.mjs"
  },
  "dependencies": {
    "@google/generative-ai": "^0.24.1",
    "@modelcontextprotocol/sdk": "^1.22.0",
    "undici": "^6.19.8",
    "zod": "^3.23.8"
  },
  "devDependencies": {
    "@modelcontextprotocol/inspector": "^0.6.0"
  }
}
```

### Create .env.mcp
```bash
# Global Gemini MCP environment (keep secret; not in git)
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL=gemini-3-pro-preview
GEMINI_MAX_OUTPUT_TOKENS=16384
```

### Create gemini-mcp.sh (Wrapper)
```bash
#!/usr/bin/env bash
set -euo pipefail

env_file="$HOME/.codex/mcp/.env.mcp"
if [[ -f "$env_file" ]]; then
  set -a
  source "$env_file"
  set +a
fi

: "${GEMINI_API_KEY:?GEMINI_API_KEY is required for Gemini MCP}"
exec node "$HOME/.codex/mcp/gemini-mcp-server.mjs"
```

Make executable:
```bash
chmod +x ~/.codex/mcp/gemini-mcp.sh
```

### Create gemini-mcp-server.mjs

```javascript
#!/usr/bin/env node
import { GoogleGenerativeAI } from "@google/generative-ai";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const apiKey = process.env.GEMINI_API_KEY;
if (!apiKey) {
  console.error("GEMINI_API_KEY is required");
  process.exit(1);
}

const modelName = process.env.GEMINI_MODEL || "gemini-3-pro-preview";
const defaultMaxOutputTokens = Number(process.env.GEMINI_MAX_OUTPUT_TOKENS) || 16384;

const client = new GoogleGenerativeAI(apiKey);

// Find file by searching upward
const findFileUpward = (filename, maxLength) => {
  let currentDir = process.cwd();
  while (true) {
    const candidate = path.join(currentDir, filename);
    if (existsSync(candidate)) {
      const raw = readFileSync(candidate, "utf8").trim();
      if (raw.length > maxLength) {
        return `${raw.slice(0, maxLength)}\n\n[truncated]`;
      }
      return raw;
    }
    const parent = path.dirname(currentDir);
    if (parent === currentDir) return null;
    currentDir = parent;
  }
};

// Find CONTEXT.md in services/<service>/
const findServiceContext = (maxLength) => {
  const cwd = process.cwd();
  const cwdParts = cwd.split(path.sep);
  const worktreesIndex = cwdParts.indexOf('worktrees');

  let serviceName = null;
  if (worktreesIndex !== -1 && cwdParts.length > worktreesIndex + 1) {
    serviceName = cwdParts[worktreesIndex + 1];
  } else {
    const dirName = path.basename(cwd);
    if (dirName.endsWith('-service')) serviceName = dirName;
  }

  if (serviceName) {
    const contextPath = path.join(cwd, 'services', serviceName, 'CONTEXT.md');
    if (existsSync(contextPath)) {
      const raw = readFileSync(contextPath, "utf8").trim();
      if (raw.length > maxLength) {
        return `${raw.slice(0, maxLength)}\n\n[truncated]`;
      }
      return raw;
    }
  }
  return findFileUpward('CONTEXT.md', maxLength);
};

const agentsContext = findFileUpward("AGENTS.md", 12000);
const contextContent = findServiceContext(8000);

const server = new Server(
  { name: "gemini-mcp", version: "0.5.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [{
    name: "gemini_generate_content",
    description: "Generate text with Gemini for planning/coding workflows.",
    inputSchema: {
      type: "object",
      properties: {
        prompt: { type: "string" },
        systemInstruction: { type: "string" },
        temperature: { type: "number" },
        maxOutputTokens: { type: "number" }
      },
      required: ["prompt"]
    }
  }]
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { arguments: args = {} } = request.params;
  const prompt = args.prompt?.trim();
  if (!prompt) return { content: [{ type: "text", text: "prompt required" }], isError: true };

  const model = client.getGenerativeModel({ model: modelName });

  const systemParts = [];
  if (agentsContext) systemParts.push(`AGENTS.md:\n${agentsContext}`);
  if (contextContent) systemParts.push(`CONTEXT.md:\n${contextContent}`);
  if (args.systemInstruction) systemParts.push(args.systemInstruction);

  const response = await model.generateContent({
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    systemInstruction: systemParts.length > 0
      ? { parts: [{ text: systemParts.join("\n\n") }] }
      : undefined,
    generationConfig: {
      temperature: args.temperature,
      maxOutputTokens: args.maxOutputTokens || defaultMaxOutputTokens
    }
  });

  const text = response?.response?.text() ?? "";
  return { content: [{ type: "text", text: text || "[Empty response]" }], isError: false };
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.error(`[Gemini MCP] Ready (model: ${modelName})`);
```

### Install Dependencies
```bash
cd ~/.codex/mcp
npm install
```

---

## Step 5: Configure Codex

Edit `~/.codex/config.toml`:

```toml
[mcp_servers.gemini]
command = "/Users/YOUR_USERNAME/.codex/mcp/gemini-mcp.sh"

[features]
rmcp_client = true

# Optional: Filesystem MCP for your repo
[mcp_servers."your-repo-fs"]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/your-repo"]
```

---

## Step 6: Create PROTOCOL.md (for Codex)

Create `~/.codex/skills/PROTOCOL.md`:

```markdown
# Codex Protocols

## g-planning
1) Codex plan with context
2) Gemini plan (always run)
3) Compare strengths/gaps
4) Unified plan

## g-coding
1) TDD implementation
2) Gemini QCHECK (always run)
3) Address findings

## g-submit
1) Git status
2) Create branch
3) Run quality gates
4) Submit PR
```

---

## Step 7: Create Repo Context Files

In your repository, create:

### AGENTS.md (repo root)
```markdown
# Best Practices

## TDD
- Stub → Test → Implement

## Writing Functions
- Keep under 50 lines
- Descriptive names
- Single responsibility

## Writing Tests
- Test edge cases
- Meaningful assertions
- Group by function
```

### services/<service>/CONTEXT.md
```markdown
# Service Context

## Architecture
- REST port: 7002
- gRPC port: 50052

## Dependencies
- PostgreSQL
- Redis

## SLOs
- p99 latency < 200ms
- Availability > 99.9%
```

---

## Testing the Setup

### Test UserPromptSubmit Hook
```bash
# In Claude Code, any prompt should now show:
# "INSTRUCTION: MANDATORY SKILL ACTIVATION SEQUENCE..."
```

### Test Gemini MCP
```bash
cd /path/to/your-repo
~/.codex/mcp/gemini-mcp.sh
# Should show: [Gemini MCP] Ready (model: gemini-3-pro-preview)
```

### Test Skills
```bash
# In Claude Code:
# "Help me plan a new feature"
# Should trigger g-planning skill
```

---

## Summary

| Component | Location | Purpose |
|-----------|----------|---------|
| UserPromptSubmit hook | `<repo>/.claude/hooks/` | Forces skill evaluation |
| Claude settings | `~/.claude/settings.json` | Hook configuration |
| Claude skills | `~/.claude/skills/g-*/` | Workflow instructions |
| Codex config | `~/.codex/config.toml` | MCP server config |
| Codex protocols | `~/.codex/skills/PROTOCOL.md` | Codex workflows |
| Gemini MCP | `~/.codex/mcp/` | Second opinion via Gemini |
| AGENTS.md | Repo root | Best practices |
| CONTEXT.md | `services/<service>/` | Service architecture |
