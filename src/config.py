import os
import sys
import json
from pathlib import Path

# Clean quotes from API keys if loaded literally from .env
for key in ["GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"]:
    if key in os.environ:
        val = os.environ[key].strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            os.environ[key] = val[1:-1]

# Determine workspace from command line argument, fallback to default
workspace_arg = None
for arg in sys.argv[1:]:
    if not arg.startswith("-"):
        workspace_arg = arg
        break

if workspace_arg:
    WORKSPACE = Path(workspace_arg).resolve()
else:
    WORKSPACE = Path("./agent_workspace").resolve()

WORKSPACE.mkdir(exist_ok=True)
CONFIG_FILE = WORKSPACE / "agent_config.json"

DEFAULT_CONFIG = {
    "selected_model": "gemini",
    "model_details": {
        "gemini": "gemini/gemini-2.5-flash",
        "claude": "anthropic/claude-3-5-sonnet-20241022",
        "groq": "groq/llama-3.3-70b-versatile",
        "local": "ollama/qwen2.5-coder:7b"
    },
    "temperature": 0.15,
    "max_history_turns": 6,
    "command_timeout": 45,
    "permission_policy": {
        "read_file": "always",
        "write_file": "ask",
        "edit_file": "ask",
        "run_command": "ask",
        "web_screenshot": "always",
        "search_codebase": "always"
    },
    "allowed_dirs": [str(WORKSPACE)]
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                for k, v in loaded.items():
                    if isinstance(v, dict) and k in cfg:
                        cfg[k].update(v)
                    else:
                        cfg[k] = v
        except Exception:
            pass
    return cfg

def save_config(new_config):
    global config
    config = new_config
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_resolved_model_id(gateway: str, model_id: str) -> str:
    if not model_id:
        return ""
    if "/" in model_id:
        return model_id
    prefixes = {
        "gemini": "gemini",
        "claude": "anthropic",
        "groq": "groq",
        "local": "ollama"
    }
    return f"{prefixes.get(gateway, gateway)}/{model_id}"

config = load_config()
