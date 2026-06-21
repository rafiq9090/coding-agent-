# Premium Custom Terminal Coding Agent

An advanced, terminal-based autonomous AI coding agent featuring the Cursor/Antigravity execution engine with granular sandbox limits, interactive setting configurations, and local & cloud model gateways (Gemini, Claude, Groq, Ollama).

---

## 🚀 Getting Started

### 1. Installation
Install the required dependencies inside your python virtual environment:
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment Keys
Add your API keys to the `.env` file in the root directory:
```bash
GEMINI_API_KEY="your-gemini-key"
ANTHROPIC_API_KEY="your-claude-key"
GROQ_API_KEY="your-groq-key"
```

### 3. Run the Agent
To start the agent:
```bash
venv/bin/python custom_agent.py
```

---

## 🛠️ Usage and Control Commands

### How to Ask Tasks
Simply type your task when prompted with `User > `:
```bash
User > create a basic python script that does calculations
```

### How to Configure Settings
Type any of the following commands at the `User > ` prompt to enter the interactive Settings Menu:
* `settings`
* `config`
* `setup`

This menu allows you to modify:
1. **Model Gateway & Specific ID**: Switch between `gemini`, `claude`, `groq`, or local `ollama` and enter custom model IDs (e.g. `groq/llama-3.3-70b-versatile`).
2. **Agent Persona**: Choose from `developer`, `qa_tester`, `orchestrator`, `database_designer`, `architecture_designer`, `planner`, and `security_engineer` to customize the system instructions.
3. **Parameters**: Modify temperature, history memory size (max turns), and command timeouts.
4. **Permissions**: Change actions like `run_command` or `write_file` to `always` allow, `ask` for permission, or `deny` entirely.
5. **Allowed Directories**: Add or remove directories outside of `./agent_workspace` to allow the agent access to other local folders.

### How to Answer Permission Prompts
When the agent executes a restricted tool (such as running a command or writing a file), it will ask for authorization:
```bash
Do you want to allow this action? (y/n) [or 'exit' to quit]:
```
* Press **`y`** to approve the single action.
* Press **`n`** to deny the single action (the agent will try to find another way).
* Type **`exit`** or **`quit`** to immediately stop and exit the agent session.

### How to Close/Exit the Agent
* At the `User > ` prompt: type `exit` or `quit`.
* At the permission prompt: type `exit` or `quit`.
* Press `Ctrl + C` at any point to cancel the running loop.

---

## 📂 Project Structure

```
my-agent/
├── custom_agent.py          # CLI Runner entry point
├── agent_workspace/         # The active sandbox directory for files
│   └── agent_config.json    # Saved configurations
└── src/
    ├── __init__.py          # Package initializer
    ├── config.py            # API key parsing & configuration loads/saves
    ├── prompts.py           # Core agent instructions and system prompts
    ├── tools.py             # Sandbox paths checker, terminal runners, playwright
    └── ui.py                # Visual console styling and Settings Menu
```
