#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import threading
from typing import Dict, Optional
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Set paths
agent_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=agent_dir / ".env")
sys.path.insert(0, str(agent_dir))

# Import config & tools
from src.config import config, save_config, get_resolved_model_id, build_messages_for_model, WORKSPACE, set_env_var
import src.tools

app = FastAPI(title="Antigravity Agent Playground")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AgentState:
    def __init__(self):
        self.messages = []
        self.status = "idle"  # idle, thinking, waiting_permission
        self.stream_buffer = ""
        self.pending_permission = None
        self.permission_event = None
        self.permission_result = False
        self.tool_logs = []
        self.should_stop = False

# Dictionary to hold states for multiple browser sessions/tabs
states: Dict[str, AgentState] = {}
states_lock = threading.Lock()

def get_session_state(session_id: str) -> AgentState:
    with states_lock:
        if session_id not in states:
            states[session_id] = AgentState()
        return states[session_id]

def append_system_log(session_id: str, log_type: str, message: str):
    s_state = get_session_state(session_id)
    with states_lock:
        s_state.tool_logs.append({
            "type": log_type,
            "message": message
        })

def gui_permission_handler(action: str, detail: str) -> bool:
    """Handle permission requests from tools.

    If the configuration key ``auto_permission`` is set to ``True`` the
    function automatically grants permission to avoid the UI from blocking
    for up to five minutes.  This is useful for development or when the
    user trusts the tool to act without manual confirmation.
    """
    # Resolve the session_id from the current thread name
    session_id = threading.current_thread().name
    s_state = get_session_state(session_id)

    # Auto‑approve when requested via config
    if config.get("auto_permission", False):
        append_system_log(session_id, "Permission", f"⚡ Auto‑approved permission: {action}")
        return True

    event = threading.Event()
    with states_lock:
        s_state.status = "waiting_permission"
        s_state.pending_permission = {
            "action": action,
            "detail": detail
        }
        s_state.permission_event = event
        s_state.permission_result = False
    
    append_system_log(session_id, "Permission", f"⚠️ Waiting for user permission: {action}")
    
    # Wait for the web client to set the event (5‑minute timeout)
    success = event.wait(timeout=300.0)
    
    with states_lock:
        result = s_state.permission_result
        s_state.pending_permission = None
        s_state.permission_event = None
        if not s_state.should_stop:
            s_state.status = "thinking"
    
    append_system_log(session_id, "Permission", f"✅ Permission decision: {'ALLOWED' if result else 'DENIED'}")
    return result if success else False

# Register override
src.tools.PERMISSION_HANDLER = gui_permission_handler

async def execute_agent_prompt():
    session_id = threading.current_thread().name
    s_state = get_session_state(session_id)
    
    from src.mcp_client import mcp_manager
    from custom_agent import (
        get_dynamic_system_prompt,
        get_resolved_model_id,
        parse_markdown_json,
        execute_tool_call
    )
    import litellm
    
    await mcp_manager.connect_servers()
    
    history = []
    with states_lock:
        # Exclude the placeholder assistant message
        history = [m for m in s_state.messages[:-1]]
        
    loop_count = 0
    while True:
        # Check for cancellation before turn start
        with states_lock:
            if s_state.should_stop:
                append_system_log(session_id, "System", "🛑 Generation cancelled by user.")
                break

        loop_count += 1
        if loop_count > 6:
            append_system_log(session_id, "System", "Notice: Reached execution limit of 6 tool calls.")
            break
            
        with states_lock:
            s_state.status = "thinking"
            
        try:
            max_turns = config.get("max_history_turns", 6)
            if len(history) > (max_turns + 1):
                active_messages = [history[0]] + history[-(max_turns):]
            else:
                active_messages = history

            # Format history messages for litellm. Support multimodal image payloads
            formatted_messages = []
            for m in active_messages:
                if m.get("role") == "user" and m.get("image_data"):
                    formatted_messages.append({
                        "role": m["role"],
                        "content": [
                            {"type": "text", "text": m["content"] or "Attached Image"},
                            {"type": "image_url", "image_url": {"url": m["image_data"]}}
                        ]
                    })
                else:
                    formatted_messages.append({
                        "role": m["role"],
                        "content": m["content"]
                    })
 
            gateway = config.get("selected_model", "gemini")
            raw_model_id = config.get("model_details", {}).get(gateway, "gemini/gemini-1.5-flash")
            active_model_id = get_resolved_model_id(gateway, raw_model_id)
            dynamic_system_prompt = await get_dynamic_system_prompt(mcp_manager)

            response = litellm.completion(
                model=active_model_id,
                messages=build_messages_for_model(
                    gateway,
                    raw_model_id,
                    dynamic_system_prompt,
                    formatted_messages,
                ),
                api_base="http://localhost:11434" if gateway == "local" else None,
                temperature=config.get("temperature", 0.15),
                stream=True,
                timeout=10.0
            )
            
            reply = ""
            for chunk in response:
                # Check for cancellation during token stream
                with states_lock:
                    if s_state.should_stop:
                        break
                content = chunk.choices[0].delta.content
                if content:
                    reply += content
                    with states_lock:
                        s_state.stream_buffer += content
                        if s_state.messages and s_state.messages[-1]["role"] == "assistant":
                            s_state.messages[-1]["content"] = s_state.stream_buffer
            
            with states_lock:
                if s_state.should_stop:
                    append_system_log(session_id, "System", "🛑 Generation aborted during token stream.")
                    break
                    
            history.append({"role": "assistant", "content": reply})
            with states_lock:
                s_state.stream_buffer = ""
                
        except Exception as e:
            err_msg = f"API Error: {e}"
            append_system_log(session_id, "System", err_msg)
            with states_lock:
                if s_state.messages and s_state.messages[-1]["role"] == "assistant":
                    s_state.messages[-1]["content"] = f"API Error encountered: {e}"
            break

        # Check for cancellation before tool execution
        with states_lock:
            if s_state.should_stop:
                append_system_log(session_id, "System", "🛑 Execution stopped before tool run.")
                break
            
        tool_call = parse_markdown_json(reply)
        if tool_call and "tool" in tool_call:
            tool_name = tool_call["tool"]
            args = tool_call.get("arguments", {})
            args_str = json.dumps(args, indent=2)
            
            append_system_log(session_id, "ToolCall", f"▶ Tool Call: {tool_name}\nArgs: {args_str}")
            
            result = await execute_tool_call(tool_name, args, mcp_manager)
            
            # Check for cancellation after tool execution
            with states_lock:
                if s_state.should_stop:
                    append_system_log(session_id, "System", f"🛑 Execution stopped after tool run ({tool_name}).")
                    break

            append_system_log(session_id, "ToolResult", f"Outcome of {tool_name}:\n{result}")
            history.append({"role": "user", "content": f"Execution Result:\n{result}"})
            
            with states_lock:
                # Add visual tool result
                s_state.messages.append({
                    "role": "system",
                    "content": f"🛠️ **Executed Tool `{tool_name}`**\n\n```\n{result[:1200]}\n```"
                })
                s_state.messages.append({"role": "assistant", "content": ""})
        else:
            break

def run_agent_in_thread(prompt: str, image_data: str, session_id: str):
    s_state = get_session_state(session_id)
    with states_lock:
        s_state.should_stop = False
        s_state.status = "thinking"
        s_state.stream_buffer = ""
        user_msg = {"role": "user", "content": prompt}
        if image_data:
            user_msg["image_data"] = image_data
        s_state.messages.append(user_msg)
        s_state.messages.append({"role": "assistant", "content": ""})
        
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(execute_agent_prompt())
    except Exception as e:
        print(f"Error in agent thread: {e}")
    finally:
        loop.close()
        with states_lock:
            s_state.status = "idle"
            s_state.stream_buffer = ""

class ChatPrompt(BaseModel):
    prompt: str
    image_data: Optional[str] = None
    session_id: str = "default"

class PermissionDecision(BaseModel):
    allow: bool
    session_id: str = "default"

class EnvUpdate(BaseModel):
    key: str
    value: str

@app.post("/api/chat")
async def chat(chat_prompt: ChatPrompt):
    session_id = chat_prompt.session_id
    s_state = get_session_state(session_id)
    if s_state.status != "idle":
        return JSONResponse({"status": "error", "message": "Agent is currently busy."}, status_code=400)
    
    # Start thread with session_id set as the thread name
    t = threading.Thread(
        target=run_agent_in_thread, 
        args=(chat_prompt.prompt, chat_prompt.image_data, session_id),
        name=session_id
    )
    t.daemon = True
    t.start()
    return {"status": "ok"}

@app.post("/api/stop")
async def stop_agent(session_id: str = "default"):
    s_state = get_session_state(session_id)
    with states_lock:
        s_state.should_stop = True
        s_state.status = "idle"
        if s_state.permission_event:
            s_state.permission_result = False
            s_state.permission_event.set()
    append_system_log(session_id, "System", "🛑 Cancellation requested by user.")
    return {"status": "ok"}

@app.get("/api/mcp/status")
async def get_mcp_status():
    try:
        from src.mcp_client import mcp_manager
        mcp_configs = config.get("mcp_servers", {})
        status_map = {}
        for name in mcp_configs.keys():
            status_map[name] = "connected" if name in mcp_manager.sessions else "disconnected"
        return status_map
    except Exception:
        return {}

@app.post("/api/mcp/reconnect")
async def reconnect_mcp():
    try:
        from src.mcp_client import mcp_manager
        await mcp_manager.disconnect_all()
        await mcp_manager.connect_servers()
        return {"status": "ok"}
    except Exception:
        return JSONResponse({"status": "error", "message": "MCP not available."}, status_code=500)

@app.post("/api/permission")
async def permission(decision: PermissionDecision):
    s_state = get_session_state(decision.session_id)
    with states_lock:
        if s_state.permission_event:
            s_state.permission_result = decision.allow
            s_state.permission_event.set()
            return {"status": "ok"}
    return JSONResponse({"status": "error", "message": "No pending permission request found."}, status_code=400)

@app.get("/api/state")
async def get_state(session_id: str = "default"):
    s_state = get_session_state(session_id)
    with states_lock:
        return {
            "status": s_state.status,
            "messages": s_state.messages,
            "stream_buffer": s_state.stream_buffer,
            "pending_permission": s_state.pending_permission,
            "tool_logs": s_state.tool_logs[-30:]
        }

@app.post("/api/clear")
async def clear_chat(session_id: str = "default"):
    s_state = get_session_state(session_id)
    with states_lock:
        s_state.messages = []
        s_state.tool_logs = []
        s_state.stream_buffer = ""
    return {"status": "ok"}

@app.get("/api/config")
async def get_web_config():
    return config

@app.post("/api/config")
async def update_web_config(req: Request):
    body = await req.json()
    save_config(body)
    return {"status": "ok"}

@app.post("/api/env")
async def update_env(item: EnvUpdate):
    set_env_var(item.key, item.value)
    return {"status": "ok"}

HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Antigravity Agent Playground</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-main: #181818;
            --bg-chat: #1e1e1e;
            --bg-input: #252525;
            --border-color: #2d2d2d;
            --text-main: #e3e3e3;
            --text-muted: #8e8e8e;
            --accent-green: #10B981;
            --accent-blue: #4f9cfc;
            --accent-yellow: #f59e0b;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-main);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        /* Classic Top Header */
        .classic-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 16px;
            background-color: var(--bg-main);
            border-bottom: 1px solid var(--border-color);
            height: 40px;
            z-index: 10;
        }

        .header-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-main);
        }

        .header-right {
            display: flex;
            gap: 12px;
        }

        .header-action-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 6px;
            border-radius: 4px;
            transition: all 0.2s;
        }

        .header-action-btn:hover {
            color: var(--text-main);
            background-color: rgba(255,255,255,0.05);
        }

        /* Main Workspace layout */
        .workspace {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        /* SIDEBAR (LEFT) - Setup & Config */
        .sidebar {
            width: 280px;
            background-color: var(--bg-main);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            padding: 16px;
            overflow-y: auto;
            transition: width 0.2s ease, padding 0.2s ease;
        }

        .sidebar.collapsed {
            width: 0;
            padding: 0;
            overflow: hidden;
            border-right: none;
        }

        .section-title {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            margin-bottom: 16px;
            font-weight: 700;
        }

        .form-group {
            margin-bottom: 16px;
        }

        .form-group label {
            display: block;
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-weight: 500;
        }

        select, input[type="text"] {
            width: 100%;
            padding: 8px 12px;
            background-color: #202020;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            color: var(--text-main);
            font-family: inherit;
            font-size: 13px;
            outline: none;
            transition: border-color 0.15s;
        }

        select:focus, input[type="text"]:focus {
            border-color: #555;
        }

        .btn {
            padding: 10px 14px;
            background-color: #2d2d2d;
            color: var(--text-main);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.15s;
            width: 100%;
            text-align: center;
        }

        .btn:hover {
            background-color: #353535;
        }

        /* MCP Status Items */
        .mcp-server-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: #202020;
            padding: 8px 10px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            font-size: 12px;
        }

        .mcp-server-name {
            font-weight: 500;
            color: var(--text-main);
        }

        .mcp-server-status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--text-muted);
        }

        .mcp-status-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
        }

        .mcp-status-dot.connected {
            background-color: var(--accent-green);
            box-shadow: 0 0 8px var(--accent-green);
        }

        .mcp-status-dot.disconnected {
            background-color: #ff4a4a;
        }

        /* CHAT AREA CONTAINER (CENTER) */
        .chat-container {
            flex: 1;
            background-color: var(--bg-chat);
            display: flex;
            flex-direction: column;
            height: 100%;
            position: relative;
            overflow: hidden;
        }

        /* Welcome Center State */
        .chat-container.welcome-state {
            justify-content: center;
            align-items: center;
        }

        .chat-container.welcome-state .chat-messages {
            display: none;
        }

        .chat-container.welcome-state .chat-input-area {
            position: static;
            width: 580px;
            max-width: 95%;
            padding: 0;
            background: transparent;
            border: none;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        /* Toast notifications */
        .toast-container {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 250;
            display: flex;
            flex-direction: column;
            gap: 10px;
            pointer-events: none;
        }

        .toast {
            background-color: #222222;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 16px;
            color: var(--text-main);
            font-size: 13px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            pointer-events: auto;
            animation: slideIn 0.3s ease-out;
            max-width: 400px;
        }

        .toast.success {
            border-color: var(--accent-green);
            color: var(--accent-green);
        }

        .toast.error {
            border-color: #ff4a4a;
            color: #ff9e9e;
        }

        .toast.warning {
            border-color: var(--accent-yellow);
            color: var(--accent-yellow);
        }

        @keyframes slideIn {
            from { transform: translateX(400px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(400px); opacity: 0; }
        }

        .toast.exiting {
            animation: slideOut 0.3s ease-in forwards;
        }

        /* Copy button for code blocks */
        .code-block-container {
            position: relative;
            margin: 8px 0;
        }

        .copy-code-btn {
            position: absolute;
            top: 8px;
            right: 8px;
            background-color: rgba(0,0,0,0.5);
            color: var(--text-muted);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
            cursor: pointer;
            opacity: 0;
            transition: all 0.15s;
        }

        .code-block-container:hover .copy-code-btn {
            opacity: 1;
        }

        .copy-code-btn:hover {
            background-color: rgba(0,0,0,0.8);
            color: var(--text-main);
            border-color: rgba(255,255,255,0.2);
        }

        .copy-code-btn.copied {
            color: var(--accent-green);
            border-color: var(--accent-green);
        }

        /* Button active states */
        .btn:active {
            transform: scale(0.98);
        }

        .header-action-btn:active {
            transform: scale(0.92);
        }

        /* Enhanced input focus states */
        select:focus, input[type="text"]:focus {
            border-color: var(--accent-blue);
            box-shadow: 0 0 0 2px rgba(79, 156, 252, 0.1);
        }

        /* Loading spinner */
        .spinner {
            display: inline-block;
            width: 12px;
            height: 12px;
            border: 2px solid rgba(255,255,255,0.2);
            border-top-color: var(--text-main);
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Message hover actions */
        .message-row {
            position: relative;
        }

        .message-row:hover .message-actions {
            opacity: 1;
        }

        .message-actions {
            position: absolute;
            right: 0;
            top: -24px;
            display: flex;
            gap: 6px;
            opacity: 0;
            transition: opacity 0.15s;
        }

        .message-action-btn {
            background-color: #2d2d2d;
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.15s;
        }

        .message-action-btn:hover {
            background-color: #353535;
            color: var(--text-main);
            border-color: #555;
        }

        .welcome-title-container {
            display: none;
        }

        .chat-container.welcome-state .welcome-title-container {
            display: block;
            text-align: left;
            width: 100%;
            font-size: 22px;
            font-weight: 600;
            color: var(--text-main);
            margin-bottom: 4px;
        }

        .welcome-suggestions {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
            width: 100%;
        }

        .suggestion-pill {
            background-color: #202020;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 12px;
            color: var(--text-muted);
            cursor: pointer;
            user-select: none;
            transition: all 0.15s;
        }

        .suggestion-pill:hover {
            border-color: #4a4a4a;
            color: var(--text-main);
            background-color: #282828;
        }

        /* Chat messages list */
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .message-row {
            display: flex;
            flex-direction: column;
            width: 100%;
        }

        .message-row.new {
            animation: fadeIn 0.15s ease-out;
        }
        .tool-message.new {
            animation: fadeIn 0.15s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-header {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 6px;
        }

        .message-content {
            font-size: 14px;
            line-height: 1.6;
            color: var(--text-main);
            word-wrap: break-word;
            white-space: pre-wrap;
        }

        /* Message attached image preview */
        .message-attached-image {
            max-width: 240px;
            max-height: 180px;
            border-radius: 8px;
            margin-top: 8px;
            border: 1px solid var(--border-color);
            cursor: pointer;
            transition: opacity 0.15s;
            object-fit: cover;
        }

        .message-attached-image:hover {
            opacity: 0.95;
        }

        /* Tool executions */
        .tool-message {
            background-color: #202020;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 12px;
            width: 100%;
            overflow: hidden;
        }

        .tool-header {
            padding: 10px 14px;
            background-color: rgba(255,255,255,0.01);
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            user-select: none;
        }

        .tool-title {
            font-size: 12px;
            font-family: var(--font-mono);
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .tool-toggle-icon {
            font-size: 11px;
            color: var(--text-muted);
            transition: transform 0.2s;
        }

        .tool-message.collapsed .tool-toggle-icon {
            transform: rotate(-90deg);
        }

        .tool-body {
            padding: 12px;
            border-top: 1px solid var(--border-color);
            background-color: rgba(0,0,0,0.15);
            max-height: 400px;
            overflow-y: auto;
        }

        .tool-message.collapsed .tool-body {
            max-height: 0;
            padding: 0;
            border-top: none;
            overflow: hidden;
        }

        .tool-body pre {
            margin: 0;
            font-family: var(--font-mono);
            font-size: 12px;
            color: var(--text-main);
        }

        /* Glowing status dots */
        .typing-loader {
            display: inline-flex;
            gap: 4px;
            align-items: center;
        }

        .typing-dot {
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: var(--text-muted);
            animation: bounce 1.2s infinite ease-in-out;
        }

        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }

        @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-3px); }
        }

        /* Floating / bottom Input Bar */
        .chat-input-area {
            padding: 16px 24px;
            background-color: var(--bg-chat);
        }

        .cursor-input-container {
            background-color: var(--bg-input);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px;
            position: relative;
            display: flex;
            flex-direction: column;
            gap: 6px;
            transition: border-color 0.15s;
        }

        .cursor-input-container:focus-within {
            border-color: #4a4a4a;
        }

        /* Image preview area inside input box */
        .image-preview-container {
            position: relative;
            display: inline-block;
            margin-bottom: 8px;
            align-self: flex-start;
        }

        .image-preview-container img {
            max-width: 80px;
            max-height: 80px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            object-fit: cover;
        }

        .remove-preview-btn {
            position: absolute;
            top: -6px;
            right: -6px;
            background-color: rgba(0,0,0,0.8);
            color: #fff;
            border: none;
            border-radius: 50%;
            width: 18px;
            height: 18px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            cursor: pointer;
            line-height: 1;
        }

        .remove-preview-btn:hover {
            background-color: #ff4a4a;
        }

        .cursor-input-container textarea {
            width: 100%;
            height: 48px;
            min-height: 48px;
            max-height: 180px;
            background: transparent;
            border: none;
            resize: none;
            color: var(--text-main);
            font-family: inherit;
            font-size: 14px;
            outline: none;
            line-height: 1.5;
            padding: 10px 8px 10px 12px;
            box-sizing: border-box;
        }

        .cursor-input-container textarea::placeholder {
            color: #555555;
        }

        .cursor-input-toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 4px;
        }

        .toolbar-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .attachment-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 6px;
            border-radius: 6px;
            transition: all 0.15s;
        }

        .attachment-btn:hover {
            color: var(--text-main);
            background-color: rgba(255,255,255,0.05);
        }

        .model-selector-pill {
            background-color: #2b2b2b;
            color: #9a9a9a;
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 4px;
            cursor: pointer;
            user-select: none;
            transition: background 0.15s, color 0.15s;
        }

        .model-selector-pill:hover {
            background-color: #333333;
            color: var(--text-main);
        }

        .status-pill {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--text-muted);
        }

        .status-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background-color: var(--accent-green);
            animation: none !important;
        }

        .status-thinking .status-dot {
            background-color: var(--accent-blue);
            animation: none !important;
        }

        .status-waiting .status-dot {
            background-color: var(--accent-yellow);
            animation: none !important;
        }

        .send-action-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 6px;
            border-radius: 6px;
            transition: all 0.15s;
        }

        .send-action-btn:hover {
            color: var(--text-main);
            background-color: rgba(255,255,255,0.05);
        }

        /* Model selector dropdown menu overlay */
        .model-dropdown-menu {
            position: absolute;
            bottom: 45px;
            left: 12px;
            background-color: #222222;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.5);
            display: none;
            flex-direction: column;
            z-index: 100;
            min-width: 170px;
            padding: 4px 0;
        }

        .model-dropdown-menu.show {
            display: flex;
        }

        .dropdown-item {
            padding: 8px 12px;
            font-size: 12.5px;
            color: var(--text-main);
            cursor: pointer;
            transition: background 0.15s;
        }

        .dropdown-item:hover {
            background-color: #2d2d2d;
        }

        /* CONSOLE PANEL (RIGHT) - Real time trace logs */
        .console-panel {
            width: 320px;
            background-color: var(--bg-main);
            border-left: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            transition: width 0.2s ease;
        }

        .console-panel.collapsed {
            width: 0;
            overflow: hidden;
            border-left: none;
        }

        .console-header {
            padding: 10px 16px;
            border-bottom: 1px solid var(--border-color);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            font-weight: 700;
        }

        .console-logs {
            flex: 1;
            padding: 16px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 12px;
            font-family: var(--font-mono);
            font-size: 11.5px;
        }

        .log-entry {
            border-left: 2px solid var(--accent-blue);
            padding-left: 8px;
        }

        .log-entry.ToolCall { border-color: var(--accent-blue); color: var(--accent-blue); }
        .log-entry.ToolResult { border-color: var(--accent-green); color: var(--text-main); }
        .log-entry.Permission { border-color: var(--accent-yellow); color: var(--accent-yellow); }
        .log-entry.System { border-color: var(--accent-red); color: #EF4444; }

        .log-entry pre {
            margin-top: 4px;
            white-space: pre-wrap;
            background: rgba(0, 0, 0, 0.2);
            padding: 6px;
            border-radius: 4px;
            border: 1px solid rgba(255,255,255,0.02);
            max-height: 200px;
            overflow-y: auto;
        }

        /* FLOATING PERMISSION MODAL OVERLAY */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.6);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 200;
        }

        .modal {
            background-color: #222222;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            width: 440px;
            max-width: 90%;
            padding: 24px;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0,0,0,0.6);
        }

        .modal-title {
            font-size: 16px;
            font-weight: 700;
            color: var(--accent-yellow);
            margin-bottom: 12px;
        }

        .modal-detail {
            font-size: 13px;
            color: var(--text-main);
            background: rgba(0,0,0,0.35);
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid var(--border-color);
            font-family: var(--font-mono);
            text-align: left;
            word-break: break-all;
            max-height: 180px;
            overflow-y: auto;
        }

        .modal-actions {
            display: flex;
            gap: 12px;
        }

        .modal-actions button {
            flex: 1;
            padding: 10px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            border: none;
            font-size: 13px;
            transition: opacity 0.15s;
        }

        .btn-deny-modal {
            background-color: #3a2222;
            color: #ff9e9e;
        }

        .btn-allow-modal {
            background-color: var(--accent-yellow);
            color: #000;
        }

        /* Scrollbars */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
    </style>
</head>
<body>

    <!-- Header Navigation -->
    <header class="classic-header">
        <div class="header-left">
            <span class="header-title">Agent</span>
        </div>
        <div class="header-right">
            <button class="header-action-btn" onclick="clearChat()" title="Clear Chat History">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            </button>
            <button class="header-action-btn" onclick="toggleSidebar()" title="Toggle Setup Configuration">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
            </button>
            <button class="header-action-btn" onclick="toggleLogs()" title="Toggle Execution Trace Logs">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
            </button>
        </div>
    </header>

    <!-- Main Workspace -->
    <div class="workspace">
        <!-- Sidebar Configuration panel (Left) -->
        <div class="sidebar" id="panel-settings">
            <h2 class="section-title">Configuration</h2>
            
            <div class="form-group">
                <label>Model Gateway</label>
                <select id="select-gateway" onchange="onGatewayChanged()">
                    <option value="gemini">Gemini</option>
                    <option value="claude">Claude (Anthropic)</option>
                    <option value="groq">Groq</option>
                    <option value="nvidia">Nvidia NIM</option>
                    <option value="local">Ollama (Local)</option>
                </select>
            </div>

            <div class="form-group">
                <label>Model Name / ID</label>
                <input type="text" id="input-model-id">
            </div>

            <div class="form-group">
                <label>System Persona</label>
                <select id="select-persona">
                    <option value="developer">Developer</option>
                    <option value="debugger">Bug Hunter</option>
                    <option value="qa">QA Tester</option>
                    <option value="security_engineer">Security Engineer</option>
                </select>
            </div>

            <div class="form-group">
                <label>NVIDIA NIM API Key</label>
                <input type="text" id="env-nvidia-key" placeholder="Enter key..." onblur="updateEnvVar('NVIDIA_API_KEY', this.value)">
            </div>

            <div class="form-group">
                <label>Groq API Key</label>
                <input type="text" id="env-groq-key" placeholder="Get free key at console.groq.com" onblur="updateEnvVar('GROQ_API_KEY', this.value)">
            </div>

            <div class="form-group">
                <label>Gemini API Key</label>
                <input type="text" id="env-gemini-key" placeholder="Enter key..." onblur="updateEnvVar('GEMINI_API_KEY', this.value)">
            </div>

            <button class="btn" onclick="saveWebConfig()">Apply Config</button>

            <!-- MCP Connection Section -->
            <div class="mcp-section" style="margin-top: 24px; border-top: 1px solid var(--border-color); padding-top: 16px;">
                <h3 class="section-title" style="font-size: 10px; margin-bottom: 12px;">MCP Servers</h3>
                <div id="mcp-servers-list" style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px;">
                    <!-- Populated dynamically -->
                </div>
                <button class="btn" onclick="reconnectMCP()" id="btn-reconnect-mcp" style="font-size: 11.5px; padding: 8px 12px;">Reconnect MCP</button>
            </div>
        </div>

        <!-- Center Chat Box -->
        <div class="chat-container welcome-state" id="panel-chat">
            <div class="chat-messages" id="chat-messages">
                <!-- Messages -->
            </div>
            
            <div class="chat-input-area" id="chat-input-area">
                <div class="welcome-title-container">my-agent</div>
                <div class="cursor-input-container">
                    <!-- Image preview inside input container -->
                    <div class="image-preview-container" id="image-preview-container" style="display: none;">
                        <img id="image-preview-img" src="" alt="preview">
                        <button class="remove-preview-btn" onclick="removeImagePreview()">&times;</button>
                    </div>

                    <textarea id="chat-input" placeholder="Ask anything, @ to mention, / for workflows" onkeydown="handleKeyDown(event)"></textarea>
                    
                    <div class="cursor-input-toolbar">
                        <div class="toolbar-left">
                            <!-- Image upload attachment button -->
                            <button class="attachment-btn" onclick="triggerImageUpload()" title="Upload Image">
                                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
                            </button>
                            <input type="file" id="image-upload-input" accept="image/*" style="display: none" onchange="handleImageUpload(event)">

                            <div class="model-selector-pill" onclick="toggleModelDropdown(event)">
                                <span id="current-model-display">Gemini</span>
                                <svg class="chevron-icon" viewBox="0 0 24 24" width="12" height="12"><path d="M7 10l5 5 5-5H7z" fill="currentColor"/></svg>
                            </div>
                            <div class="status-pill" id="status-pill">
                                <span class="status-dot"></span>
                                <span id="status-text">Idle</span>
                            </div>
                        </div>
                        <div class="toolbar-right">
                            <button class="send-action-btn" id="send-action-btn" onclick="handleSendOrStop()" title="Send Prompt">
                                <svg viewBox="0 0 24 24" width="16" height="16"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" fill="currentColor"/></svg>
                            </button>
                        </div>
                    </div>

                    <!-- Model Dropdown Overlay -->
                    <div class="model-dropdown-menu" id="model-dropdown-menu">
                        <div class="dropdown-item" onclick="selectModelGateway('gemini')">Gemini</div>
                        <div class="dropdown-item" onclick="selectModelGateway('claude')">Claude (Anthropic)</div>
                        <div class="dropdown-item" onclick="selectModelGateway('groq')">Groq</div>
                        <div class="dropdown-item" onclick="selectModelGateway('nvidia')">Nvidia NIM</div>
                        <div class="dropdown-item" onclick="selectModelGateway('local')">Ollama (Local)</div>
                    </div>
                </div>

                <div class="welcome-suggestions" id="welcome-suggestions">
                    <div class="suggestion-pill" onclick="clickSuggestion('check current repository git status')">🌿 Check Git Status</div>
                    <div class="suggestion-pill" onclick="clickSuggestion('run a security check scan')">🛡️ Security Audit</div>
                    <div class="suggestion-pill" onclick="clickSuggestion('list the contents of the root folder')">📁 Workspace Files</div>
                </div>
            </div>
        </div>

        <!-- Right Side Terminal Log panel -->
        <div class="console-panel" id="panel-logs">
            <div class="console-header">Execution logs</div>
            <div class="console-logs" id="console-logs">
                <!-- Real-time logs -->
            </div>
        </div>
    </div>

    <!-- Floating Permission Modal Dialog -->
    <div class="modal-overlay" id="modal-overlay">
        <div class="modal">
            <div class="modal-title">Permission Request</div>
            <div class="modal-detail" id="modal-detail">
                <!-- Details -->
            </div>
            <div class="modal-actions">
                <button class="btn-deny-modal" onclick="submitPermission(false)">Deny</button>
                <button class="btn-allow-modal" onclick="submitPermission(true)">Allow</button>
            </div>
        </div>
    </div>

    <!-- Toast Notifications -->
    <div class="toast-container" id="toast-container"></div>
    <script>
        // ============================================
        // TOAST NOTIFICATION SYSTEM
        // ============================================
        function showToast(message, type = 'info', duration = 3000) {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.textContent = message;
            container.appendChild(toast);

            if (duration > 0) {
                setTimeout(() => {
                    toast.classList.add('exiting');
                    setTimeout(() => toast.remove(), 300);
                }, duration);
            }
            return toast;
        }

        // ============================================
        // MAIN APP STATE
        // ============================================
        let sessionId = window.name;
        if (!sessionId || !sessionId.startsWith("playground_tab_")) {
            sessionId = "playground_tab_" + (window.crypto && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2, 15) + Date.now().toString(36));
            window.name = sessionId;
        }

        let agentStatus = "idle";
        let activeConfig = {};
        let previousMsgCount = 0;
        let lastRenderedMessagesJSON = null;
        let lastStreamBuffer = "";
        let uploadedImageBase64 = null;
        let pollInterval = null;
        let mcpPollInterval = null;

        // ============================================
        // CONFIG & STATE MANAGEMENT
        // ============================================
        async function fetchConfig() {
            try {
                let res = await fetch("/api/config");
                activeConfig = await res.json();
                
                document.getElementById("select-gateway").value = activeConfig.selected_model;
                document.getElementById("select-persona").value = activeConfig.persona;
                
                onGatewayChanged();
                await pollMCPStatus();
                showToast("Configuration loaded", "success", 1500);
            } catch(e) {
                console.error(e);
                showToast("Failed to load configuration", "error", 3000);
            }
        }

        function onGatewayChanged() {
            // Keep this handler minimal: update the gateway label.
            const sel = document.getElementById("select-gateway");
            const display = document.getElementById("current-model-display");
            if (sel && display) display.innerText = sel.options[sel.selectedIndex].text || sel.value;
        }

        function triggerImageUpload() {
            const fileInput = document.getElementById("image-upload-input");
            if (fileInput) fileInput.click();
        }

        function handleImageUpload(event) {
            const file = event.target.files && event.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = () => {
                uploadedImageBase64 = reader.result;
                const previewContainer = document.getElementById("image-preview-container");
                const previewImg = document.getElementById("image-preview-img");
                if (previewImg) previewImg.src = uploadedImageBase64;
                if (previewContainer) previewContainer.style.display = "flex";
            };
            reader.onerror = () => {
                showToast("Failed to read image file", "error", 3000);
            };
            reader.readAsDataURL(file);
        }

        function removeImagePreview() {
            uploadedImageBase64 = null;
            const previewContainer = document.getElementById("image-preview-container");
            const previewImg = document.getElementById("image-preview-img");
            const fileInput = document.getElementById("image-upload-input");
            if (previewImg) previewImg.src = "";
            if (previewContainer) previewContainer.style.display = "none";
            if (fileInput) fileInput.value = "";
        }

        function clickSuggestion(promptText) {
            document.getElementById("chat-input").value = promptText;
            document.getElementById("chat-input").focus();
            sendPrompt();
        }

        async function sendPrompt() {
            if (agentStatus !== "idle") {
                showToast("Agent is currently busy", "warning", 2000);
                return;
            }
            
            let inp = document.getElementById("chat-input");
            let prompt = inp.value.trim();
            if (!prompt && !uploadedImageBase64) {
                showToast("Please enter a message or attach an image", "warning", 2000);
                return;
            }

            let imageToSend = uploadedImageBase64;
            inp.value = "";
            removeImagePreview();
            
            document.getElementById("panel-chat").classList.remove("welcome-state");

            try {
                await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ 
                        prompt: prompt,
                        image_data: imageToSend,
                        session_id: sessionId
                    })
                });
                inp.focus();
            } catch(e) {
                showToast("Failed to send message", "error");
                inp.value = prompt;
                if (imageToSend) uploadedImageBase64 = imageToSend;
            }
        }

        async function stopAgent() {
            try {
                await fetch(`/api/stop?session_id=${sessionId}`, { method: "POST" });
                showToast("Generation stopped", "warning", 1500);
            } catch(e) {
                showToast("Failed to stop generation", "error");
            }
        }

        function handleSendOrStop() {
            if (agentStatus === "idle") {
                sendPrompt();
            } else {
                stopAgent();
            }
        }

        function handleKeyDown(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                handleSendOrStop();
            }
        }

        async function submitPermission(allow) {
            document.getElementById("modal-overlay").style.display = "none";
            try {
                await fetch("/api/permission", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ allow, session_id: sessionId })
                });
            } catch(e) {
                showToast("Failed to submit permission", "error");
            }
        }

        // ============================================
        // UI PANEL TOGGLES
        // ============================================
        function toggleSidebar() {
            const sidebar = document.getElementById("panel-settings");
            sidebar.classList.toggle("collapsed");
            showToast(sidebar.classList.contains("collapsed") ? "Config hidden" : "Config shown", "info", 1000);
        }

        function toggleLogs() {
            const logs = document.getElementById("panel-logs");
            logs.classList.toggle("collapsed");
            showToast(logs.classList.contains("collapsed") ? "Logs hidden" : "Logs shown", "info", 1000);
        }

        function toggleTool(headerElement) {
            let container = headerElement.closest('.tool-message');
            container.classList.toggle('collapsed');
        }

        // ============================================
        // COPY TO CLIPBOARD
        // ============================================
        function copyToClipboard(text, btn) {
            navigator.clipboard.writeText(text).then(() => {
                const originalText = btn.textContent;
                btn.textContent = "✓ Copied";
                btn.classList.add("copied");
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.classList.remove("copied");
                }, 2000);
                showToast("Copied to clipboard", "success", 1500);
            }).catch(err => {
                showToast("Failed to copy", "error");
            });
        }

        // ============================================
        // STATE POLLING
        // ============================================
        async function pollState() {
            try {
                let res = await fetch(`/api/state?session_id=${sessionId}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                let data = await res.json();

                agentStatus = data.status;
                updateStatusUI(data.status);

                let modal = document.getElementById("modal-overlay");
                if (data.status === "waiting_permission" && data.pending_permission) {
                    document.getElementById("modal-detail").innerHTML = `
                        <strong>Tool Action:</strong> ${escapeHtml(data.pending_permission.action)}<br><br>
                        <strong>Detail:</strong> ${escapeHtml(data.pending_permission.detail)}
                    `;
                    modal.style.display = "flex";
                } else {
                    modal.style.display = "none";
                }

                if (data.messages.length === 0) {
                    document.getElementById("panel-chat").classList.add("welcome-state");
                } else {
                    document.getElementById("panel-chat").classList.remove("welcome-state");
                    renderChat(data.messages, data.status, data.stream_buffer);
                }

                renderLogs(data.tool_logs);
            } catch(e) {
                console.error("Poll error:", e);
            }
        }

        async function pollMCPStatus() {
            try {
                let res = await fetch("/api/mcp/status");
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                let data = await res.json();
                let listDiv = document.getElementById("mcp-servers-list");
                let html = "";
                for (let name in data) {
                    let status = data[name];
                    let isConnected = (status === "connected");
                    let dotClass = isConnected ? "connected" : "disconnected";
                    let label = isConnected ? "Connected" : "Disconnected";
                    html += `
                        <div class="mcp-server-item">
                            <span class="mcp-server-name">${escapeHtml(name)}</span>
                            <span class="mcp-server-status">
                                <span class="mcp-status-dot ${dotClass}"></span>
                                <span>${label}</span>
                            </span>
                        </div>
                    `;
                }
                if (Object.keys(data).length === 0) {
                    html = `<div style="font-size:12px; color:var(--text-muted);">No MCP servers configured.</div>`;
                }
                listDiv.innerHTML = html;
            } catch(e) {
                console.error("MCP poll error:", e);
            }
        }

        async function reconnectMCP() {
            let btn = document.getElementById("btn-reconnect-mcp");
            const originalText = btn.innerText;
            btn.innerText = "Reconnecting...";
            btn.disabled = true;
            try {
                await fetch("/api/mcp/reconnect", { method: "POST" });
                await pollMCPStatus();
                showToast("MCP servers reconnected", "success", 2000);
            } catch(e) {
                console.error(e);
                showToast("Failed to reconnect MCP servers", "error");
            } finally {
                btn.innerText = originalText;
                btn.disabled = false;
            }
        }

        function updateStatusUI(status) {
            let pill = document.getElementById("status-pill");
            let text = document.getElementById("status-text");
            let sendBtn = document.getElementById("send-action-btn");

            pill.className = "status-pill";
            if (status === "idle") {
                pill.classList.add("status-idle");
                text.innerText = "Idle";
                sendBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" fill="currentColor"/></svg>`;
                sendBtn.title = "Send Prompt";
            } else {
                if (status === "thinking") {
                    pill.classList.add("status-thinking");
                    text.innerText = "Thinking...";
                } else if (status === "waiting_permission") {
                    pill.classList.add("status-waiting");
                    text.innerText = "Needs Permission";
                }
                sendBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="4" y="4" width="16" height="16" rx="2" fill="currentColor"/></svg>`;
                sendBtn.title = "Stop Generation";
            }
        }

        function renderChat(messages, status, streamBuffer) {
            let chatDiv = document.getElementById("chat-messages");

            // Try to avoid full DOM rebuilds by computing a lightweight structural
            // signature for the messages. Streaming content is represented by
            // a stable token so transient token appends don't change the sig.
            try {
                let simplified = messages.map((m, idx) => {
                    if (m.role === 'assistant' && idx === messages.length - 1 && status === 'thinking') {
                        return { role: m.role, content: '__STREAM__' };
                    }
                    return { role: m.role, content: m.content };
                });
                let sig = JSON.stringify(simplified);
                if (lastRenderedMessagesJSON === sig) {
                    if (lastStreamBuffer !== streamBuffer) {
                        lastStreamBuffer = streamBuffer;
                        let rows = chatDiv.querySelectorAll('.message-row, .tool-message');
                        if (rows.length > 0) {
                            let lastRow = rows[rows.length - 1];
                            let header = lastRow.querySelector('.message-header');
                            if (header && header.textContent.trim().toLowerCase().startsWith('agent')) {
                                let contentDiv = lastRow.querySelector('.message-content');
                                if (contentDiv) {
                                    if (streamBuffer && streamBuffer.length > 0 && status === 'thinking') {
                                        contentDiv.innerHTML = escapeHtml(streamBuffer).replace(/\n/g, '<br>');
                                    }
                                }
                            }
                        }
                    }
                    return;
                }
                lastRenderedMessagesJSON = sig;
                lastStreamBuffer = streamBuffer;
            } catch (e) {
                lastRenderedMessagesJSON = null;
            }

            // Full rebuild (only when structure actually changed)
            let currentHTML = "";
            messages.forEach((msg, idx) => {
                let isNew = idx >= previousMsgCount;
                if (msg.role === "user") {
                    let attachedImageHTML = "";
                    if (msg.image_data) attachedImageHTML = `<br><img src="${msg.image_data}" class="message-attached-image" onclick="window.open(this.src)">`;
                    currentHTML += `
                        <div class="${isNew ? 'message-row new' : 'message-row'}">
                            <div class="message-header">User</div>
                            <div class="message-content">${escapeHtml(msg.content)}${attachedImageHTML}</div>
                        </div>`;
                } else if (msg.role === "assistant") {
                    let isLast = (idx === messages.length - 1);
                    let content = msg.content || "";
                    if (isLast && status === "thinking" && !content && streamBuffer && streamBuffer.length > 0) {
                        currentHTML += `
                            <div class="${isNew ? 'message-row new' : 'message-row'}">
                                <div class="message-header">Agent</div>
                                <div class="message-content">${escapeHtml(streamBuffer).replace(/\n/g,'<br>')}</div>
                            </div>`;
                    } else {
                        let formatted = escapeHtml(content).replace(/\n/g, "<br>");
                        formatted = formatted.replace(/```([\s\S]*?)```/g, (match, code) => {
                            return `<div class="code-block-container"><button class="copy-code-btn" onclick="copyToClipboard(\`${code.replace(/`/g, '\\`')}\`, this)">Copy</button><pre style="background:#222; padding:10px; border-radius:6px; font-family:var(--font-mono); font-size:12.5px; margin: 8px 0; overflow-x:auto; border: 1px solid var(--border-color);">${code}</pre></div>`;
                        });
                        currentHTML += `
                            <div class="${isNew ? 'message-row new' : 'message-row'}">
                                <div class="message-header">Agent</div>
                                <div class="message-content">${formatted}</div>
                            </div>`;
                    }
                } else if (msg.role === "system") {
                    let titleMatch = msg.content.match(/🛠️ \*\*Executed Tool \`(.*?)\`\*\*/);
                    let toolName = titleMatch ? titleMatch[1] : "execute_tool";
                    let codeBlocks = msg.content.match(/```([\s\S]*?)```/);
                    let codeContent = codeBlocks ? codeBlocks[1] : msg.content;
                    currentHTML += `
                        <div class="${isNew ? 'tool-message collapsed new' : 'tool-message collapsed'}">
                            <div class="tool-header" onclick="toggleTool(this)">
                                <div class="tool-title">
                                    <span>⚙️</span> Executed Tool: ${escapeHtml(toolName)}
                                </div>
                                <div class="tool-toggle-icon">▼</div>
                            </div>
                            <div class="tool-body">
                                <div class="code-block-container">
                                    <button class="copy-code-btn" onclick="copyToClipboard(\`${codeContent.replace(/`/g, '\\`')}\`, this)">Copy</button>
                                    <pre>${escapeHtml(codeContent)}</pre>
                                </div>
                            </div>
                        </div>`;
                }
            });

            if (chatDiv.innerHTML !== currentHTML) {
                let shouldScroll = (chatDiv.scrollHeight - chatDiv.scrollTop - chatDiv.clientHeight) < 80;
                chatDiv.innerHTML = currentHTML;
                if (shouldScroll || previousMsgCount !== messages.length) {
                    chatDiv.scrollTop = chatDiv.scrollHeight;
                    previousMsgCount = messages.length;
                }
            }
        }

        function renderLogs(logs) {
            let logDiv = document.getElementById("console-logs");
            let logHTML = "";

            logs.forEach(log => {
                logHTML += `
                    <div class="log-entry ${log.type}">
                        <strong>[${log.type.toUpperCase()}]</strong>
                        <pre>${escapeHtml(log.message)}</pre>
                    </div>
                `;
            });

            if (logDiv.innerHTML !== logHTML) {
                logDiv.innerHTML = logHTML;
                logDiv.scrollTop = logDiv.scrollHeight;
            }
        }

        function escapeHtml(text) {
            if (!text) return "";
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        // ============================================
        // INITIALIZATION
        // ============================================
        window.addEventListener("load", () => {
            fetchConfig();
            pollInterval = setInterval(pollState, 400);
            mcpPollInterval = setInterval(pollMCPStatus, 2000);
            showToast("Agent playground loaded", "success", 1500);
        });

        window.addEventListener("beforeunload", () => {
            if (pollInterval) clearInterval(pollInterval);
            if (mcpPollInterval) clearInterval(mcpPollInterval);
        });
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(content=HTML_CONTENT)

def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

if __name__ == "__main__":
    main()
