import subprocess
import json
from pathlib import Path
from src.config import config, WORKSPACE
from src.ui import console, Confirm, Panel

def check_permission(action: str, detail: str) -> bool:
    """Interceptors to check user defined rules before running dangerous tools"""
    policy = config["permission_policy"].get(action, "ask")
    if policy == "always":
        return True
    if policy == "deny":
        console.print(f"[bold red]Blocked:[/bold red] Action '{action}' is denied by your permissions config.")
        return False
    
    # Prompt the user for explicit permission
    console.print(Panel(f"[yellow]{detail}[/yellow]", title=f"Permission Required: {action.upper()}"))
    return Confirm.ask("Do you want to allow this action?")

def resolve_path(relative_path: str) -> Path:
    """Resolves and keeps paths inside the designated workspace container"""
    target_path = Path(relative_path)
    if not target_path.is_absolute():
        target_path = (WORKSPACE / target_path).resolve()
    else:
        target_path = target_path.resolve()
        
    # Security Sandbox Check across all allowed directories
    allowed = False
    for d in config.get("allowed_dirs", [str(WORKSPACE)]):
        try:
            if str(target_path).startswith(str(Path(d).resolve())):
                allowed = True
                break
        except Exception:
            pass
            
    if not allowed:
        raise PermissionError(f"Path access blocked: {relative_path} lies outside allowed directories.")
    return target_path

def tool_read_file(path: str) -> str:
    try:
        real_path = resolve_path(path)
        if not real_path.exists():
            return f"Error: File '{path}' does not exist."
        with open(real_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

def tool_write_file(path: str, content: str) -> str:
    if not check_permission("write_file", f"Write file '{path}'"):
        return "Permission denied by user."
    try:
        real_path = resolve_path(path)
        real_path.parent.mkdir(parents=True, exist_ok=True)
        with open(real_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote file to '{path}'"
    except Exception as e:
        return f"Error writing file: {e}"

def tool_edit_file(path: str, search_block: str, replace_block: str) -> str:
    if not check_permission("edit_file", f"Edit file '{path}'"):
        return "Permission denied by user."
    try:
        real_path = resolve_path(path)
        if not real_path.exists():
            return f"Error: File '{path}' does not exist."
        with open(real_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if search_block not in content:
            return "Error: Could not find the exact code block to edit. Double check indentation and spaces."
            
        new_content = content.replace(search_block, replace_block, 1)
        with open(real_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Successfully applied edits to '{path}'"
    except Exception as e:
        return f"Error editing file: {e}"

def tool_run_command(command: str) -> str:
    if not check_permission("run_command", f"Run Terminal Command: {command}"):
        return "Permission denied by user."
    try:
        timeout_val = config.get("command_timeout", 45)
        
        # Prepend the virtual environment bin path to environment PATH
        import os
        import sys
        env = os.environ.copy()
        venv_bin = Path(sys.executable).parent
        if (venv_bin / "python").exists():
            env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"

        # Run process inside the workspace directory
        res = subprocess.run(
            command,
            shell=True,
            cwd=str(WORKSPACE),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_val
        )
        output = f"Exit Code: {res.returncode}\n"
        if res.stdout:
            output += f"STDOUT:\n{res.stdout}\n"
        if res.stderr:
            output += f"STDERR:\n{res.stderr}\n"
        return output
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout_val} seconds."
    except Exception as e:
        return f"Error executing command: {e}"

async def tool_web_screenshot(url: str) -> str:
    """Uses Playwright to visually verify app render in headless mode"""
    if not check_permission("web_screenshot", f"Visual check at: {url}"):
        return "Permission denied by user."
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Error: playwright package not installed. Run 'pip install playwright' and 'playwright install'."
        
    try:
        import shutil
        executable_path = None
        for binary in ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium", "chrome"]:
            found = shutil.which(binary)
            if found:
                executable_path = found
                break

        async with async_playwright() as p:
            launch_kwargs = {"headless": True}
            if executable_path:
                launch_kwargs["executable_path"] = executable_path
                
            browser = await p.chromium.launch(**launch_kwargs)
            page = await browser.new_page()
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            
            await page.goto(url, wait_until="networkidle", timeout=10000)
            screenshot_path = WORKSPACE / "screenshot.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            title = await page.title()
            await browser.close()
            
            err_text = "\n".join(errors) if errors else "No JS console errors."
            return f"Successfully loaded page: '{title}'.\nConsole output/errors:\n{err_text}\nScreenshot saved inside workspace."
    except Exception as e:
        return f"Error loading browser page: {e}"

class PlaywrightBrowser:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    async def get_page(self):
        if self.page and not self.page.is_closed():
            return self.page
        
        from playwright.async_api import async_playwright
        import shutil
        executable_path = None
        for binary in ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium", "chrome"]:
            found = shutil.which(binary)
            if found:
                executable_path = found
                break

        self.playwright = await async_playwright().start()
        launch_kwargs = {"headless": False}
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
            
        try:
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)
        except Exception:
            # Fallback to headless mode if headful fails (e.g., no display)
            launch_kwargs["headless"] = True
            self.browser = await self.playwright.chromium.launch(**launch_kwargs)
            
        self.page = await self.browser.new_page()
        return self.page

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.page = None
        self.browser = None
        self.playwright = None

browser_manager = PlaywrightBrowser()

async def tool_web_browse_navigate(url: str) -> str:
    """Navigate to a URL in the active browser session."""
    if not check_permission("web_browse_navigate", f"Browser navigate to: {url}"):
        return "Permission denied by user."
    try:
        page = await browser_manager.get_page()
        await page.goto(url, wait_until="networkidle", timeout=15000)
        title = await page.title()
        current_url = page.url
        return f"Successfully navigated to '{current_url}'. Page Title: '{title}'."
    except Exception as e:
        return f"Error navigating to {url}: {e}"

async def tool_web_browse_click(selector: str) -> str:
    """Click an element matching the selector (CSS selector or text content)."""
    if not check_permission("web_browse_click", f"Browser click: {selector}"):
        return "Permission denied by user."
    try:
        page = await browser_manager.get_page()
        await page.click(selector, timeout=5000)
        return f"Successfully clicked element '{selector}'."
    except Exception as e:
        return f"Error clicking element '{selector}': {e}"

async def tool_web_browse_type(selector: str, text: str) -> str:
    """Type text into an input field or element matching the selector."""
    if not check_permission("web_browse_type", f"Browser type '{text}' into: {selector}"):
        return "Permission denied by user."
    try:
        page = await browser_manager.get_page()
        await page.fill(selector, text, timeout=5000)
        return f"Successfully typed '{text}' into element '{selector}'."
    except Exception as e:
        return f"Error typing into element '{selector}': {e}"

async def tool_web_browse_get_elements() -> str:
    """Retrieve clickable links, buttons, and inputs on the current page to decide interaction target."""
    try:
        page = await browser_manager.get_page()
        elements = await page.evaluate("""() => {
            const items = [];
            document.querySelectorAll('a, button, input, textarea, [role="button"]').forEach((el, index) => {
                const text = el.innerText || el.placeholder || el.value || '';
                const type = el.tagName.toLowerCase();
                let sel = el.id ? `#${el.id}` : el.tagName.toLowerCase();
                if (el.className) {
                    sel += '.' + Array.from(el.classList).join('.');
                }
                if (text.trim()) {
                    items.push({ index, type, text: text.trim().substring(0, 50), selector: sel });
                }
            });
            return items.slice(0, 40);
        }""")
        
        if not elements:
            return "No prominent interactive elements found on the current page."
            
        res = "Interactive elements found:\n"
        for item in elements:
            res += f"- [{item['type'].upper()}] Text: '{item['text']}' -> Selector: '{item['selector']}'\n"
        return res
    except Exception as e:
        return f"Error getting elements: {e}"

async def tool_web_browse_screenshot() -> str:
    """Capture a screenshot of the current active browser page."""
    if not check_permission("web_browse_screenshot", "Browser capture screenshot"):
        return "Permission denied by user."
    try:
        page = await browser_manager.get_page()
        screenshot_path = WORKSPACE / "screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        return f"Screenshot successfully saved to '{screenshot_path}'."
    except Exception as e:
        return f"Error capturing screenshot: {e}"

async def tool_web_browse_close() -> str:
    """Close the active browser session."""
    try:
        await browser_manager.close()
        return "Browser session successfully closed."
    except Exception as e:
        return f"Error closing browser: {e}"

def tool_search_codebase(query_text: str) -> str:
    """Uses ChromaDB vector search if present; falls back to basic word matches"""
    try:
        # Fallback keyword match
        matches = []
        for file in WORKSPACE.rglob("*"):
            if file.is_file() and not file.name.startswith(".") and "node_modules" not in file.parts and "__pycache__" not in file.parts:
                try:
                    with open(file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines):
                        if query_text.lower() in line.lower():
                            matches.append(f"{file.relative_to(WORKSPACE)}:L{idx+1} -> {line.strip()}")
                except Exception:
                    pass
        if not matches:
            return "No keyword matches found."
        return "\n".join(matches[:20])
    except Exception as e:
        return f"Search failed: {e}"

# List of tools metadata sent to the model
TOOLS_METADATA = [
    {
        "name": "read_file",
        "description": "Read file contents inside the workspace.",
        "arguments": ["path"]
    },
    {
        "name": "write_file",
        "description": "Write new file or overwrite existing contents inside the workspace.",
        "arguments": ["path", "content"]
    },
    {
        "name": "edit_file",
        "description": "Edit/replace specific chunks in a file using a search and replace block.",
        "arguments": ["path", "search_block", "replace_block"]
    },
    {
        "name": "run_command",
        "description": "Run terminal bash command inside the workspace directory.",
        "arguments": ["command"]
    },
    {
        "name": "web_screenshot",
        "description": "Launch headless browser to render a URL and check JavaScript errors.",
        "arguments": ["url"]
    },
    {
        "name": "search_codebase",
        "description": "Search the codebase for specific text matches.",
        "arguments": ["query_text"]
    },
    {
        "name": "web_browse_navigate",
        "description": "Navigate to a URL in the active browser session.",
        "arguments": ["url"]
    },
    {
        "name": "web_browse_click",
        "description": "Click an element matching the selector (CSS selector or text content).",
        "arguments": ["selector"]
    },
    {
        "name": "web_browse_type",
        "description": "Type text into an input field or element matching the selector.",
        "arguments": ["selector", "text"]
    },
    {
        "name": "web_browse_get_elements",
        "description": "Retrieve clickable links, buttons, and inputs on the current page to decide interaction target.",
        "arguments": []
    },
    {
        "name": "web_browse_screenshot",
        "description": "Capture a screenshot of the current active browser page.",
        "arguments": []
    },
    {
        "name": "web_browse_close",
        "description": "Close the active browser session.",
        "arguments": []
    }
]
