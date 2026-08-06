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
NVIDIA_API_KEY="your-nvidia-key"
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
1. **Model Gateway & Specific ID**: Switch between `gemini`, `claude`, `groq`, `nvidia`, or local `ollama` and enter custom model IDs (e.g. `groq/llama-3.3-70b-versatile`).
2. **API Keys**: Configure API keys interactively and save them directly to the `.env` file.
3. **Agent Persona**: Choose from `developer`, `qa_tester`, `orchestrator`, `database_designer`, `architecture_designer`, `planner`, and `security_engineer` to customize the system instructions.
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
│   ├── agent_config.json    # Saved configurations
│   └── skills/              # Custom python tools/skills folder
└── src/
    ├── __init__.py          # Package initializer
    ├── config.py            # API key parsing & configuration loads/saves
    ├── prompts.py           # Core agent instructions and system prompts
    ├── tools.py             # Sandbox paths checker, terminal runners, playwright
    └── ui.py                # Visual console styling and Settings Menu
```

---

## 💡 Dynamically Loaded Custom Skills

You can easily extend the capabilities of the agent without modifying its core code by dropping Python files into `agent_workspace/skills/`.

### How to Create a Custom Skill
Every file in `agent_workspace/skills/` (e.g. `my_skill.py`) must implement two functions:
1. `get_metadata()`: Returns a dictionary describing the tool name, description, and list of expected arguments.
2. `execute(...)`: The handler function executed when the agent calls the tool (supports both sync and async definitions).

Example (`agent_workspace/skills/example_skill.py`):
```python
def get_metadata():
    return {
        "name": "greet_user",
        "description": "A custom skill that greets the user with a name.",
        "arguments": ["name"]
    }

def execute(name: str) -> str:
    return f"Hello {name}! This is a dynamically loaded custom skill."
```

The agent automatically discovers these files at runtime, registers them in its dynamic system prompt, and routes the execution calls to them on the fly.
