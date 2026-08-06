# Antigravity Agent - VS Code Extension

🤖 Copilot-style AI Agent integrated directly into VS Code with real-time chat, tool execution, and permission management.

## Features

✅ **Chat Interface** - Multi-turn conversations with your AI agent  
✅ **Tool Execution** - Automatic tool calling (git, file operations, etc.)  
✅ **Permission System** - User approval for sensitive operations  
✅ **Real-time Logging** - See all agent activities in real-time  
✅ **Multiple Models** - Support for Groq, Gemini, Claude, Ollama, Nvidia NIM  
✅ **Sidebar Control** - Quick access panel in VS Code explorer  
✅ **Webview Integration** - Full GUI inside VS Code  

## Installation

### Option 1: Install from VSIX File
```bash
# Navigate to the extension folder
cd vscode-extension

# Install the pre-built extension
code --install-extension antigravity-agent-1.0.0.vsix
```

### Option 2: Install from Source
```bash
# Clone/navigate to the project
cd /path/to/my-agent/vscode-extension

# Install dependencies
npm install

# Open in VS Code and press F5 to run the extension in debug mode
```

### Option 3: Package and Install
```bash
# Install vsce (VS Code Extension CLI)
npm install -g vsce

# Package the extension
vsce package

# Install the generated .vsix file
code --install-extension antigravity-agent-1.0.0.vsix
```

## Usage

### 1. Start the Agent
- Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
- Type: **"Open Antigravity Agent"**
- Press Enter

### 2. Configure the Agent (in the left sidebar)
- Select a **Model Gateway** (Groq, Gemini, Claude, Ollama, Nvidia NIM)
- Enter your **API Key** (if needed)
- Select a **System Persona** (Developer, Bug Hunter, QA Tester, Security Engineer)
- Click **"Apply Config"**

### 3. Chat with the Agent
- Type a message in the chat input
- Press Enter or click Send
- The agent will respond and suggest tools to execute

### 4. Manage Permissions
- When the agent wants to execute a tool, a permission modal appears
- Click **"Allow"** to execute
- Click **"Deny"** to reject

### 5. View Logs
- The right panel shows real-time execution logs
- Click the log icon to expand/collapse the logs panel

## Configuration

### API Keys

**Groq (Free)**
1. Visit: https://console.groq.com
2. Sign up (takes 2 minutes)
3. Copy your API key
4. Paste in "Groq API Key" field in the extension
5. Click "Apply Config"

**Gemini (Free tier)**
1. Visit: https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key
4. Paste in "Gemini API Key" field

**Local Ollama (No API key needed)**
- Download Ollama: https://ollama.ai
- Run: `ollama serve`
- Select "Ollama (Local)" in the extension
- No API key needed!

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line in message |
| `Escape` | Close permission modal |
| `Ctrl+Shift+P` | Command palette |

## Architecture

```
extension.js
├── activate() - Registers commands and views
├── AgentSidebarProvider - Sidebar UI component
├── startGuiServer() - Launches Python FastAPI server
└── openWebview() - Creates webview panel
        ↓
    gui_server.py (Python FastAPI)
        ├── /api/chat - Send messages
        ├── /api/state - Get chat state
        ├── /api/config - Manage config
        └── /api/permission - Handle permissions
```

## Troubleshooting

### "Server connection failed"
- Make sure port 8000 is not in use
- Check if `gui_server.py` dependencies are installed
- Run: `pip install fastapi uvicorn litellm pydantic python-dotenv`

### "API Key not recognized"
- Make sure the API key is valid
- Check if you're using the correct model gateway
- Try a different model (Groq is free and reliable)

### "Permission timeout"
- The permission request times out after 5 minutes
- Click "Deny" or "Allow" to dismiss

### Extension not showing
- Make sure VS Code is reloaded: `Ctrl+Shift+P` → "Developer: Reload Window"
- Check extension is enabled in VS Code Extensions view

## Development

### File Structure
```
vscode-extension/
├── extension.js           # Main extension code
├── package.json           # Extension manifest
├── LICENSE
├── README.md
└── SETUP.md              # This file
```

### Debugging
1. Open `vscode-extension` folder in VS Code
2. Press `F5` to start debug session
3. A new VS Code window will open with the extension
4. Check debug console for logs

### Packaging
```bash
# Install vsce
npm install -g vsce

# Package
vsce package

# Publish to marketplace (requires publisher account)
vsce publish
```

## License

See LICENSE file

## Support

For issues and feature requests, visit:
https://github.com/your-username/my-agent

---

**Made with ☄️ by Antigravity**
