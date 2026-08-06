# 🤖 Antigravity Agent - Quick Start Guide

## What We Built

A **Copilot-style AI Agent Extension for VS Code** that brings the full Antigravity Agent GUI directly into your editor!

### Features at a Glance

```
┌─────────────────────────────────────────┐
│  VS Code                                │
│  ┌───────────────────────────────────┐  │
│  │  Agent Control Panel (Sidebar)    │  │
│  │  ✓ Open Agent                     │  │
│  │  ✓ Stop Server                    │  │
│  │  ✓ Status Indicator               │  │
│  └───────────────────────────────────┘  │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  Antigravity Agent Webview Panel  │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │ Config │ Chat │ Logs        │  │  │
│  │  ├─────────────────────────────┤  │  │
│  │  │ You: Check git status       │  │  │
│  │  │ Agent: Checking...          │  │  │
│  │  │ [Tool: git_control]         │  │  │
│  │  │ [ALLOW] [DENY]              │  │  │
│  │  └─────────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Installation (Choose One)

### ⚡ Method 1: Use Pre-built Extension (Easiest)
```bash
cd /home/rafiq/allProject/my-agent/vscode-extension
code --install-extension antigravity-agent-1.0.0.vsix
```

### 🔨 Method 2: Install from Source
```bash
cd /home/rafiq/allProject/my-agent/vscode-extension
npm install
# Press F5 in VS Code (opens debug window with extension)
```

### 📦 Method 3: Package Yourself
```bash
npm install -g vsce
cd /home/rafiq/allProject/my-agent/vscode-extension
vsce package
code --install-extension antigravity-agent-*.vsix
```

## First Run

### 1️⃣ Open the Agent
- Press `Ctrl+Shift+P` (Cmd+Shift+P on Mac)
- Type: `Open Antigravity Agent`
- Press Enter

**What happens:**
- Python server starts automatically
- Agent panel opens in a new sidebar
- Full GUI loads from http://127.0.0.1:8000

### 2️⃣ Configure API Keys

**Choose one model:**

| Model | Setup | Speed | Cost |
|-------|-------|-------|------|
| **Groq** | Get free key at console.groq.com | ⚡⚡ Fast | FREE |
| **Gemini** | Get key at aistudio.google.com | ⚡ Medium | FREE tier |
| **Ollama** | Download ollama.ai, run ollama serve | ⚡ Depends | FREE |
| **Claude** | Anthropic API (paid) | ⚡⚡ Fast | $$$ |

**Steps:**
1. Get your API key
2. Paste it in the config field
3. Click "Apply Config"

### 3️⃣ Start Chatting

**Type in the chat input:**
```
Check git status
```

**Agent will:**
1. ✅ Understand your request
2. 📋 Plan the action (git_control)
3. ⚠️ Ask for permission
4. ✅ Execute if allowed
5. 📊 Show results

## Key Commands

### Command Palette (`Ctrl+Shift+P`)
```
Open Antigravity Agent    - Launch the agent
Stop Agent Server         - Stop the Python server
```

### Keyboard Shortcuts
```
Enter              - Send message
Shift+Enter        - New line in message
Tab                - Click config/logs toggle buttons
Escape             - Close permission modal
```

## UI Layout Explained

### Left Sidebar: Configuration
```
[Model Gateway] ▼ Groq
[Model ID] groq/llama-3.3-70b-versatile
[Persona] ▼ Developer
[Groq API Key] [Enter key...]
[Apply Config] ◀────── Click this after changes
[MCP Servers] Connected ● Disconnected ●
```

### Center: Chat Area
```
User:  "Check git status"
Agent: "Checking repository status..."
[Tool Execution Card] (Click to expand)
  ⚙️ Executed Tool: git_control
  ├─ Status: On branch main
  └─ Changes: 3 files modified
```

### Right Panel: Execution Logs
```
[TOOLCALL] ▶ Tool Call: git_control
[PERMISSION] ⚠️ Waiting for permission
[PERMISSION] ✅ Permission decision: ALLOWED
[TOOLRESULT] Outcome of git_control: Exit Code 0
[SYSTEM] Generation complete
```

## How It Works

```
You type message in VS Code
         ↓
Extension sends to gui_server.py (FastAPI)
         ↓
Server connects to AI Model (Groq/Gemini/etc)
         ↓
Model generates response + tool calls
         ↓
Permission modal appears for approval
         ↓
Tool executes (git, file ops, etc)
         ↓
Results shown in chat + logs
```

## Troubleshooting

### "Can't connect to server"
```bash
# Reinstall dependencies
cd /path/to/my-agent
pip install --break-system-packages fastapi uvicorn litellm pydantic python-dotenv

# Start server manually
python3 gui_server.py
```

### "API key not working"
- Double-check the key from your provider
- Try Groq (it's free and reliable)
- Make sure you clicked "Apply Config"

### "Permission timeout"
- Click "Deny" to reject
- Try again with a simpler request

### Extension not showing
- Reload VS Code: `Ctrl+Shift+P` → "Developer: Reload Window"
- Check Extensions view (Ctrl+Shift+X)

## What You Can Do

### Chat
- ✅ Ask questions
- ✅ Get code explanations
- ✅ Request features
- ✅ Debug issues

### Execute Tools
- ✅ Git operations (status, commit, push)
- ✅ File operations (read, write, delete)
- ✅ Shell commands
- ✅ Web searches
- ✅ Custom tools via MCP

### Manage Permissions
- ✅ Approve/deny tool execution
- ✅ See detailed execution logs
- ✅ Understand what agent is doing
- ✅ Revoke permissions anytime

## Next Steps

### Explore Advanced Features
- [Read Full Documentation](./vscode-extension/SETUP.md)
- [Check Agent Capabilities](./README.md)
- [MCP Servers Setup](./agent_workspace/CLAUDE.md)

### Customize
- Edit `extension.js` to change UI
- Modify `gui_server.py` to add features
- Create custom tools via MCP

### Share
- Package and distribute via VS Code Marketplace
- Share .vsix file with team
- Integrate into your workflow

---

**Enjoy your AI-powered coding assistant!** 🚀
