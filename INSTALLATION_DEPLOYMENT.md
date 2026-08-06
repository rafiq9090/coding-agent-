# 📦 Installation & Deployment Guide

## What You Have

You now have a **complete AI Agent system** with two ways to use it:

### 1. **Web UI** (What you're using now)
- 🌐 Full-featured browser interface
- 🚀 Works on http://127.0.0.1:8000
- ✅ All features working perfectly

### 2. **VS Code Extension** (New!)
- 🤖 Copilot-style integration in VS Code
- 📦 Pre-built .vsix file included
- ⚡ One-click installation

---

## 🚀 Quick Start (5 minutes)

### Step 1: Choose Your Model

**Option A: Groq (Recommended - Free)**
1. Go to: https://console.groq.com
2. Sign up (takes 2 minutes)
3. Copy your API key
4. Paste in web UI or VS Code extension
5. Click "Apply Config"

**Option B: Local Ollama (No API key)**
1. Download: https://ollama.ai
2. Run: `ollama serve`
3. Select "Ollama (Local)" in agent
4. Done!

**Option C: Gemini (Free tier)**
1. Go to: https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Copy and paste in agent
4. Click "Apply Config"

### Step 2: Use the Web UI (Current)
```bash
# Already running at http://127.0.0.1:8000
# Just chat with the agent!
```

### Step 3: Install VS Code Extension (Optional)
```bash
# Copy the extension
cp /home/rafiq/allProject/my-agent/vscode-extension/antigravity-agent-1.0.0.vsix .

# Install it
code --install-extension antigravity-agent-1.0.0.vsix

# Reload VS Code (Ctrl+Shift+P → Reload Window)

# Done! Open with Ctrl+Shift+P → "Open Antigravity Agent"
```

---

## 📋 Installation Methods

### Method 1: Pre-built Extension (Easiest)
```bash
# One-command install
code --install-extension /home/rafiq/allProject/my-agent/vscode-extension/antigravity-agent-1.0.0.vsix
```

### Method 2: Build from Source
```bash
# Install Node.js first (if needed)
# Then:
cd /home/rafiq/allProject/my-agent/vscode-extension
npm install
npm run vscode:prepublish
vsce package
code --install-extension antigravity-agent-1.0.0.vsix
```

### Method 3: Dev Mode (For developers)
```bash
cd /home/rafiq/allProject/my-agent/vscode-extension
npm install
code .
# Press F5 to start debug session
# Extension opens in new VS Code window
```

---

## ✅ Verification Checklist

### Web UI Running?
```bash
curl http://127.0.0.1:8000
# Should return HTML
```

### Dependencies Installed?
```bash
python3 -c "import fastapi, uvicorn, litellm; print('✓ All good')"
# If error, run:
pip install --break-system-packages fastapi uvicorn litellm pydantic python-dotenv
```

### API Key Working?
1. Get a free Groq key at https://console.groq.com
2. Paste in web UI
3. Click "Apply Config"
4. Try sending a message
5. Should respond within 2 seconds

### VS Code Extension Installed?
1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X)
3. Search for "Antigravity"
4. Should see "Antigravity Agent - Copilot Style"

---

## 📂 Files Overview

### Core Files
```
gui_server.py                    - FastAPI server (ENHANCED)
vscode-extension/
├── extension.js                - VS Code extension (404 lines)
├── package.json                - Extension config (UPDATED)
├── antigravity-agent-1.0.0.vsix- Pre-built extension (READY)
└── SETUP.md                    - Setup guide
```

### Documentation
```
README.md                        - Project overview
COMPLETION_SUMMARY.md            - What we built
VSCODE_EXTENSION_GUIDE.md        - Quick start guide
INSTALLATION_DEPLOYMENT.md       - This file
```

---

## 🔧 Configuration Files

### Web UI Config
```json
// Saved in ~/.config/Code/User or browser storage
{
  "selected_model": "groq",
  "model_details": {
    "groq": "groq/llama-3.3-70b-versatile",
    "gemini": "gemini/gemini-1.5-flash"
  },
  "persona": "developer",
  "auto_permission": false,
  "max_history_turns": 6
}
```

### Environment Variables
```bash
export GROQ_API_KEY="your-key"
export GEMINI_API_KEY="your-key"
export NVIDIA_API_KEY="your-key"
```

---

## 🐛 Troubleshooting

### "Cannot connect to server"
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill existing process
kill -9 <PID>

# Restart
python3 gui_server.py
```

### "API Key not working"
```bash
# Test key directly
python3 -c "
from litellm import completion
response = completion(
    model='groq/llama-3.3-70b-versatile',
    messages=[{'role': 'user', 'content': 'Hi'}]
)
print(response)
"
```

### "Extension not showing in VS Code"
```bash
# 1. Reload VS Code
Ctrl+Shift+P → Developer: Reload Window

# 2. Check extension is enabled
Ctrl+Shift+X → Search "Antigravity"

# 3. If not there, reinstall
code --uninstall-extension antigravity-agent
code --install-extension antigravity-agent-1.0.0.vsix
```

### "Server starts but UI doesn't load"
```bash
# Check dependencies
pip list | grep -E 'fastapi|uvicorn|litellm'

# If missing, install
pip install --break-system-packages fastapi uvicorn litellm pydantic

# Restart server
python3 gui_server.py
```

---

## 🚀 Advanced Usage

### Custom API Endpoints
Edit `gui_server.py` to add:
```python
@app.post("/api/custom")
async def custom_endpoint(request: Request):
    # Your code
    return {"status": "ok"}
```

### Add Custom Tools
See `src/tools.py` to create tools like:
- File operations
- Git commands
- Web searches
- Custom scripts

### Deploy to Production
```bash
# Use production ASGI server (gunicorn)
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker gui_server:app --bind 0.0.0.0:8000

# Or use Docker
docker build -t antigravity-agent .
docker run -p 8000:8000 antigravity-agent
```

---

## 📊 System Requirements

### Minimum
- Python 3.8+
- VS Code 1.80.0+
- 4GB RAM
- 500MB disk space

### Recommended
- Python 3.10+
- VS Code 1.90.0+
- 8GB RAM
- 2GB disk space (for models)

### For Local Models (Ollama)
- GPU with 8GB+ VRAM (optional, but much faster)
- Or CPU mode (slower but works)

---

## 📝 Checklists

### First-Time Setup
- [ ] Python dependencies installed
- [ ] API key obtained (Groq/Gemini)
- [ ] Server started (`python3 gui_server.py`)
- [ ] Browser opens to http://127.0.0.1:8000
- [ ] Chat response received
- [ ] VS Code extension installed (optional)

### Before Deployment
- [ ] All dependencies in requirements.txt
- [ ] API keys configured
- [ ] Port 8000 accessible
- [ ] Firewall rules configured
- [ ] Logging enabled
- [ ] Error handling tested

### After Installation
- [ ] Test chat functionality
- [ ] Test tool execution
- [ ] Test permission system
- [ ] Check logs display
- [ ] Verify config persistence
- [ ] Try all model gateways

---

## 📞 Support Resources

### Quick Links
- **Groq API**: https://console.groq.com
- **Gemini API**: https://aistudio.google.com/app/apikey
- **Ollama**: https://ollama.ai
- **VS Code Extension Docs**: https://code.visualstudio.com/api

### Common Commands
```bash
# Check Python
python3 --version

# Install dependencies
pip install --break-system-packages -r requirements.txt

# Run server
cd /home/rafiq/allProject/my-agent
python3 gui_server.py

# Check logs
tail -f /tmp/agent.log

# Stop server
pkill -f "gui_server.py"
```

---

## 🎯 What's Next?

### Immediate (Today)
1. ✅ Install extension or use web UI
2. ✅ Get API key from Groq
3. ✅ Test agent with chat

### Short-term (This week)
- [ ] Integrate into your workflow
- [ ] Create custom tools
- [ ] Set up auto-start script
- [ ] Configure permissions policy

### Long-term (This month)
- [ ] Publish to VS Code Marketplace
- [ ] Add more model providers
- [ ] Build team sharing features
- [ ] Create documentation site

---

## 📌 Important Notes

1. **Port 8000**: Default port for web UI. Change in `gui_server.py` if needed.
2. **API Keys**: Store in `.env` file, never commit to git.
3. **Permissions**: Always verify what agent will execute before allowing.
4. **Logs**: Check execution logs to understand what happened.
5. **Firewall**: Open port 8000 if running remotely.

---

## ✨ You're All Set!

Everything is ready to use. Choose your preferred way:

**Web UI:**
```bash
python3 gui_server.py
# Open: http://127.0.0.1:8000
```

**VS Code Extension:**
```bash
code --install-extension antigravity-agent-1.0.0.vsix
# Ctrl+Shift+P → "Open Antigravity Agent"
```

**Happy coding with AI!** 🚀

---

Last Updated: 2026-07-02
Status: Production Ready ✅
