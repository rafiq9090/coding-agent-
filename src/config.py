import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List

# Clean quotes from API keys if loaded literally from .env
for key in ["GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"]:
    if key in os.environ:
        val = os.environ[key].strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            os.environ[key] = val[1:-1]

# Sync NVIDIA_API_KEY to NVIDIA_NIM_API_KEY for LiteLLM routing
if "NVIDIA_API_KEY" in os.environ and os.environ["NVIDIA_API_KEY"]:
    os.environ["NVIDIA_NIM_API_KEY"] = os.environ["NVIDIA_API_KEY"]

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
        "nvidia": "nvidia_nim/meta/llama-3.1-70b-instruct",
        "local": "ollama/qwen2.5-coder:7b"
    },
    "persona": "developer",
    "temperature": 0.15,
    "max_history_turns": 6,
    "command_timeout": 45,
    "permission_policy": {
        "read_file": "always",
        "write_file": "ask",
        "edit_file": "ask",
        "run_command": "ask",
        "web_screenshot": "always",
        "search_codebase": "always",
        "security_check": "always",
        "git_control": "ask",
        "http_request": "ask"
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

def set_env_var(key: str, value: str):
    val = value.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    
    os.environ[key] = val
    
    # Sync NVIDIA keys
    if key == "NVIDIA_API_KEY":
        os.environ["NVIDIA_NIM_API_KEY"] = val
    elif key == "NVIDIA_NIM_API_KEY":
        os.environ["NVIDIA_API_KEY"] = val
    
    env_path = Path(__file__).resolve().parent.parent / ".env"
    lines = []
    if env_path.exists():
        with open(env_path, "r") as f:
            lines = f.readlines()
            
    updated = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}=\"{val}\"\n")
            updated = True
        else:
            new_lines.append(line)
            
    if not updated:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key}=\"{val}\"\n")
        
    with open(env_path, "w") as f:
        f.writelines(new_lines)

def get_resolved_model_id(gateway: str, model_id: str) -> str:
    if not model_id:
        return ""
    
    # Map 'nvidia/' prefix to 'nvidia_nim/' for LiteLLM routing compatibility
    if model_id.startswith("nvidia/"):
        model_id = "nvidia_nim/" + model_id[len("nvidia/"):]
        
    if gateway == "nvidia" and not model_id.startswith("nvidia_nim/"):
        return f"nvidia_nim/{model_id}"
        
    if "/" in model_id:
        return model_id
        
    prefixes = {
        "gemini": "gemini",
        "claude": "anthropic",
        "groq": "groq",
        "nvidia": "nvidia_nim",
        "local": "ollama"
    }
    return f"{prefixes.get(gateway, gateway)}/{model_id}"


def should_send_system_messages(gateway: str, model_id: str) -> bool:
    resolved_model_id = get_resolved_model_id(gateway, model_id)
    try:
        from litellm.utils import supports_system_messages
        provider = "nvidia_nim" if gateway == "nvidia" else None
        return supports_system_messages(resolved_model_id, provider)
    except Exception:
        return True


def merge_system_prompt_as_user(system_prompt: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not messages:
        return [{"role": "user", "content": system_prompt}]

    first = messages[0].copy()
    if first.get("role") == "user":
        if isinstance(first.get("content"), list):
            first["content"] = [{"type": "text", "text": system_prompt}] + first["content"]
        else:
            first["content"] = f"{system_prompt}\n\n{first['content']}"
        return [first] + messages[1:]

    return [{"role": "user", "content": system_prompt}] + messages


def build_messages_for_model(
    gateway: str,
    model_id: str,
    system_prompt: str,
    formatted_messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if should_send_system_messages(gateway, model_id):
        return [{"role": "system", "content": system_prompt}] + formatted_messages
    return merge_system_prompt_as_user(system_prompt, formatted_messages)

# Initialize module-level config export for other modules.
config = load_config()

