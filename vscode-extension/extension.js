const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');

let serverProcess = null;
let agentPanel = null;

function activate(context) {
    console.log('Antigravity Agent Extension is now active.');

    // Command: Open Agent
    const openAgentCmd = vscode.commands.registerCommand('antigravity-agent.openAgent', function () {
        startGuiServer(() => {
            openWebview();
        });
    });

    // Command: Stop Agent
    const stopAgentCmd = vscode.commands.registerCommand('antigravity-agent.stopAgent', function () {
        if (serverProcess) {
            serverProcess.kill();
            serverProcess = null;
            vscode.window.showInformationMessage('Antigravity Agent server stopped.');
        }
    });

    // Sidebar View Provider
    const sidebarProvider = new AgentSidebarProvider(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            'antigravityAgentSidebar',
            sidebarProvider
        )
    );

    context.subscriptions.push(openAgentCmd, stopAgentCmd);
    
    // Auto-start on activation
    startGuiServer(() => {
        console.log('GUI Server ready');
    });
}

class AgentSidebarProvider {
    constructor(extensionUri) {
        this.extensionUri = extensionUri;
    }

    resolveWebviewView(webviewView, context, _token) {
        webviewView.webview.options = {
            enableScripts: true,
            enableCommandUris: true,
        };

        webviewView.webview.html = this.getHtmlForWebview(webviewView.webview);
    }

    getHtmlForWebview(webview) {
        return `
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        background-color: #1e1e1e;
                        color: #e0e0e0;
                        padding: 12px;
                    }
                    .container { padding: 8px 0; }
                    .section-title {
                        font-size: 11px;
                        font-weight: 700;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                        color: #858585;
                        margin-bottom: 12px;
                    }
                    .button {
                        width: 100%;
                        padding: 8px 12px;
                        background-color: #0e639c;
                        color: #fff;
                        border: none;
                        border-radius: 4px;
                        font-size: 12px;
                        font-weight: 600;
                        cursor: pointer;
                        transition: background 0.2s;
                    }
                    .button:hover {
                        background-color: #1177bb;
                    }
                    .button.stop {
                        background-color: #a61e1e;
                    }
                    .button.stop:hover {
                        background-color: #c81e1e;
                    }
                    .info {
                        font-size: 12px;
                        color: #858585;
                        margin-top: 12px;
                        line-height: 1.5;
                    }
                    .status {
                        display: flex;
                        align-items: center;
                        gap: 6px;
                        font-size: 12px;
                        margin-top: 8px;
                    }
                    .status-dot {
                        width: 8px;
                        height: 8px;
                        border-radius: 50%;
                        background-color: #4ec9b0;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="section-title">Antigravity Agent</div>
                    <button class="button" onclick="openAgent()">Open Agent Panel</button>
                    <button class="button stop" onclick="stopAgent()" style="margin-top: 8px;">Stop Server</button>
                    <div class="info">
                        💡 Open the agent in a dedicated panel to chat, execute tools, and manage permissions.
                    </div>
                    <div class="status">
                        <span class="status-dot"></span>
                        <span>Ready to chat</span>
                    </div>
                </div>
                <script>
                    const vscode = acquireVsCodeApi();
                    function openAgent() {
                        vscode.postMessage({ command: 'openAgent' });
                    }
                    function stopAgent() {
                        vscode.postMessage({ command: 'stopAgent' });
                    }
                </script>
            </body>
            </html>
        `;
    }
}

function startGuiServer(callback) {
    // Check if port 8000 is already active
    const req = http.get('http://127.0.0.1:8000/api/state', (res) => {
        // Already running
        console.log('GUI Server already running');
        callback();
    });

    req.on('error', () => {
        vscode.window.showInformationMessage('Starting Antigravity Agent server...');
        
        const workspaceFolder = vscode.workspace.workspaceFolders 
            ? vscode.workspace.workspaceFolders[0].uri.fsPath 
            : null;
            
        if (!workspaceFolder) {
            vscode.window.showErrorMessage('Please open a workspace folder to launch the agent.');
            return;
        }

        const serverScript = path.join(workspaceFolder, 'gui_server.py');
        
        // Try different Python paths
        const pythonCandidates = [
            path.join(workspaceFolder, 'venv', 'bin', 'python3'),
            path.join(workspaceFolder, 'venv', 'bin', 'python'),
            'python3',
            'python'
        ];

        let pythonPath = pythonCandidates[0];
        for (const candidate of pythonCandidates) {
            if (fs.existsSync(candidate)) {
                pythonPath = candidate;
                break;
            }
        }

        serverProcess = cp.spawn(pythonPath, [serverScript], {
            cwd: workspaceFolder,
            env: { ...process.env, PYTHONPATH: workspaceFolder }
        });

        serverProcess.stdout.on('data', (data) => {
            console.log(`[Agent Server] ${data}`);
        });

        serverProcess.stderr.on('data', (data) => {
            console.error(`[Agent Server Error] ${data}`);
        });

        serverProcess.on('close', (code) => {
            console.log(`Agent server stopped with code ${code}`);
            serverProcess = null;
        });

        setTimeout(() => {
            callback();
        }, 2500);
    });

    req.on('error', (e) => {
        console.log('Server check error:', e.message);
    });
}

function openWebview() {
    if (agentPanel) {
        agentPanel.reveal(vscode.ViewColumn.Beside);
        return;
    }

    agentPanel = vscode.window.createWebviewPanel(
        'antigravityAgent',
        '🤖 Antigravity Agent',
        vscode.ViewColumn.Beside,
        {
            enableScripts: true,
            enableCommandUris: true,
            retainContextWhenHidden: true,
            localResourceRoots: []
        }
    );

    agentPanel.webview.html = getWebviewContent();

    // Handle panel disposal
    agentPanel.onDidDispose(() => {
        agentPanel = null;
    });

    // Message handling
    agentPanel.webview.onDidReceiveMessage(
        message => {
            switch (message.command) {
                case 'openAgent':
                    vscode.commands.executeCommand('antigravity-agent.openAgent');
                    break;
                case 'stopAgent':
                    vscode.commands.executeCommand('antigravity-agent.stopAgent');
                    break;
            }
        },
        undefined,
        []
    );
}

function getWebviewContent() {
    return `
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Antigravity Agent</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                
                html, body {
                    width: 100%;
                    height: 100%;
                    overflow: hidden;
                    background-color: #1e1e1e;
                    color: #e0e0e0;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }
                
                .container {
                    width: 100%;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><defs><pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(255,255,255,0.03)" stroke-width="0.5"/></pattern></defs><rect width="100%" height="100%" fill="%231e1e1e"/><rect width="100%" height="100%" fill="url(%23grid)"/></svg>');
                }
                
                .header {
                    padding: 16px;
                    border-bottom: 1px solid rgba(255,255,255,0.1);
                    background: linear-gradient(180deg, rgba(20,20,30,0.8) 0%, rgba(20,20,30,0.4) 100%);
                    backdrop-filter: blur(10px);
                }
                
                .header-title {
                    font-size: 18px;
                    font-weight: 700;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }
                
                .header-subtitle {
                    font-size: 12px;
                    color: #858585;
                    margin-top: 4px;
                }
                
                .content {
                    flex: 1;
                    overflow: hidden;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    padding: 24px;
                    text-align: center;
                }
                
                .message {
                    font-size: 14px;
                    color: #b0b0b0;
                    line-height: 1.6;
                    max-width: 400px;
                }
                
                .loading {
                    display: inline-block;
                    width: 4px;
                    height: 4px;
                    background: #0e639c;
                    border-radius: 50%;
                    animation: pulse 1.5s infinite;
                    margin-left: 4px;
                }
                
                .loading.dot2 { animation-delay: 0.3s; }
                .loading.dot3 { animation-delay: 0.6s; }
                
                @keyframes pulse {
                    0%, 100% { opacity: 0.3; }
                    50% { opacity: 1; }
                }
                
                iframe {
                    width: 100%;
                    height: 100%;
                    border: none;
                    background: #1e1e1e;
                }
                
                .iframe-container {
                    flex: 1;
                    width: 100%;
                    overflow: hidden;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="header-title">🤖 Antigravity Agent</div>
                    <div class="header-subtitle">Connected to Local GUI Server</div>
                </div>
                <div class="iframe-container" id="iframeContainer">
                    <div class="content">
                        <div class="message">
                            Loading agent<span class="loading"></span><span class="loading dot2"></span><span class="loading dot3"></span>
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                // Load the iframe once
                setTimeout(() => {
                    const container = document.getElementById('iframeContainer');
                    container.innerHTML = '<iframe src="http://127.0.0.1:8000/"></iframe>';
                }, 1000);
            </script>
        </body>
        </html>
    `;
}

function deactivate() {
    if (serverProcess) {
        serverProcess.kill();
        serverProcess = null;
    }
    if (agentPanel) {
        agentPanel.dispose();
        agentPanel = null;
    }
}

module.exports = {
    activate,
    deactivate
};
