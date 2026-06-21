import subprocess
import json
import re
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

import asyncio

class PersistentShell:
    def __init__(self):
        self.process = None
        self.cwd = str(WORKSPACE)

    async def get_process(self):
        if self.process and self.process.returncode is None:
            return self.process
            
        import os
        import sys
        
        env = os.environ.copy()
        venv_bin = Path(sys.executable).parent
        if (venv_bin / "python").exists():
            env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
            
        self.process = await asyncio.create_subprocess_exec(
            "bash",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            cwd=self.cwd
        )
        return self.process

    async def run_command(self, command: str, timeout: float = 45.0) -> str:
        proc = await self.get_process()
        
        sentinel = "___SHELL_SENTINEL_OK___"
        status_check = f"echo {sentinel} $?"
        
        full_input = f"{command}\n{status_check}\n"
        proc.stdin.write(full_input.encode("utf-8"))
        await proc.stdin.drain()
        
        output_lines = []
        exit_code = 0
        
        async def read_stdout():
            nonlocal exit_code
            while True:
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                if sentinel in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            exit_code = int(parts[-1])
                        except ValueError:
                            pass
                    break
                output_lines.append(line)

        try:
            await asyncio.wait_for(read_stdout(), timeout=timeout)
            output = "".join(output_lines)
            status_desc = f"Exit Code: {exit_code}\n"
            if output:
                status_desc += f"STDOUT/STDERR:\n{output}"
            else:
                status_desc += "No output (Command executed successfully)."
            return status_desc
        except asyncio.TimeoutExpired:
            await self.close()
            return f"Error: Command timed out after {timeout} seconds. Persistent shell was reset."

    async def close(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception:
                pass
            self.process = None

persistent_shell = PersistentShell()

async def tool_run_command(command: str) -> str:
    if not check_permission("run_command", f"Run Terminal Command: {command}"):
        return "Permission denied by user."
    try:
        timeout_val = config.get("command_timeout", 45)
        return await persistent_shell.run_command(command, timeout=timeout_val)
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
        self.context = None
        self.page = None
        self.viewport = {"width": 1280, "height": 720}
        self.user_agent = None

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
            
        context_kwargs = {
            "viewport": self.viewport
        }
        if self.user_agent:
            context_kwargs["user_agent"] = self.user_agent
            
        self.context = await self.browser.new_context(**context_kwargs)
        self.page = await self.context.new_page()
        return self.page

    async def close(self):
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        self.page = None
        self.context = None
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

async def tool_web_browse_scroll(direction: str, amount: int = 500) -> str:
    """Scroll the page in a direction ('up', 'down', 'top', 'bottom') by a specified pixel amount."""
    try:
        page = await browser_manager.get_page()
        if direction == "down":
            await page.evaluate(f"window.scrollBy(0, {amount})")
            return f"Scrolled down by {amount} pixels."
        elif direction == "up":
            await page.evaluate(f"window.scrollBy(0, -{amount})")
            return f"Scrolled up by {amount} pixels."
        elif direction == "bottom":
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return "Scrolled to the bottom of the page."
        elif direction == "top":
            await page.evaluate("window.scrollTo(0, 0)")
            return "Scrolled to the top of the page."
        else:
            return f"Unknown direction '{direction}'. Use 'up', 'down', 'top', or 'bottom'."
    except Exception as e:
        return f"Error scrolling: {e}"

async def tool_web_browse_get_text() -> str:
    """Retrieve the visible innerText of the current page to analyze content, headers, paragraphs, and details."""
    try:
        page = await browser_manager.get_page()
        text = await page.evaluate("document.body.innerText")
        if not text.strip():
            return "The page is empty or contains no visible text."
        return f"Page Text Content (truncated to 8000 chars):\n\n{text[:8000]}"
    except Exception as e:
        return f"Error retrieving page text: {e}"

async def tool_web_browse_set_viewport(width: int, height: int, is_mobile: bool = False) -> str:
    """Set the browser window/viewport size and optionally emulate mobile device mode."""
    if not check_permission("web_browse_set_viewport", f"Set viewport to {width}x{height} (mobile={is_mobile})"):
        return "Permission denied by user."
    try:
        browser_manager.viewport = {"width": width, "height": height}
        if is_mobile:
            browser_manager.user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        else:
            browser_manager.user_agent = None
            
        # Recreate page/context if browser is already open
        if browser_manager.page:
            url = browser_manager.page.url
            await browser_manager.close()
            page = await browser_manager.get_page()
            if url and url != "about:blank":
                await page.goto(url, wait_until="networkidle", timeout=15000)
        else:
            await browser_manager.get_page()
            
        return f"Successfully updated viewport to {width}x{height} (mobile emulation: {is_mobile})."
    except Exception as e:
        return f"Error setting viewport: {e}"

async def tool_web_browse_evaluate(javascript: str) -> str:
    """Evaluate custom JavaScript in the context of the page and return the result."""
    if not check_permission("web_browse_evaluate", f"Evaluate custom JS: {javascript}"):
        return "Permission denied by user."
    try:
        page = await browser_manager.get_page()
        result = await page.evaluate(javascript)
        return f"JavaScript execution result:\n{result}"
    except Exception as e:
        return f"Error evaluating JavaScript: {e}"

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

def load_custom_skills() -> dict:
    """Dynamically load python custom skills from the 'skills' directory inside the workspace."""
    import importlib.util
    import inspect
    
    skills_dir = WORKSPACE / "skills"
    skills_dir.mkdir(exist_ok=True)
    
    # Create an example skill if none exist
    example_skill = skills_dir / "example_skill.py"
    if not any(skills_dir.glob("*.py")):
        with open(example_skill, "w", encoding="utf-8") as f:
            f.write('''# Example custom skill file.
# You can add any python file here with get_metadata() and execute() functions.
# The agent will dynamically load and register it as an available tool.

def get_metadata():
    return {
        "name": "greet_user",
        "description": "A custom skill that greets the user with a name.",
        "arguments": ["name"]
    }

def execute(name: str) -> str:
    return f"Hello {name}! This is a dynamically loaded custom skill."
''')

    skills = {}
    for filepath in skills_dir.glob("*.py"):
        if filepath.name.startswith("_") or filepath.name.startswith("."):
            continue
        try:
            module_name = filepath.stem
            spec = importlib.util.spec_from_file_location(module_name, str(filepath))
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if hasattr(module, "get_metadata") and hasattr(module, "execute"):
                meta = module.get_metadata()
                if isinstance(meta, dict) and "name" in meta and "description" in meta:
                    skills[meta["name"]] = {
                        "metadata": meta,
                        "execute": module.execute
                    }
        except Exception as e:
            pass
            
    return skills

def tool_security_check() -> str:
    """Scan the workspace for potential security issues (exposed credentials, dangerous functions, file exposures)."""
    try:
        findings = []
        
        # 1. Check for exposed secrets
        secret_patterns = {
            "NVIDIA API Key": r"nvapi-[A-Za-z0-9\-_]{64,}",
            "OpenAI API Key": r"sk-[A-Za-z0-9]{48}",
            "GitHub Token": r"ghp_[A-Za-z0-9]{36,40}",
            "Generic Private Key": r"-----BEGIN [A-Z ]+ PRIVATE KEY-----",
            "General API Key / Password Assignment": r"(?:api_key|password|secret|pass|token|key)\s*=\s*['\"][A-Za-z0-9\-_]{16,}['\"]"
        }
        
        # 2. Check for dangerous functions
        dangerous_patterns = {
            "eval() function usage": r"\beval\s*\(",
            "exec() function usage": r"\bexec\s*\(",
            "unsafe subprocess with shell=True": r"\bsubprocess\.(?:run|Popen|call|check_output)\s*\(.*shell\s*=\s*True",
            "raw os.system usage": r"\bos\.system\s*\("
        }
        
        # Scan files
        for file in WORKSPACE.rglob("*"):
            if file.is_file() and not file.name.startswith(".") and "node_modules" not in file.parts and "__pycache__" not in file.parts and "venv" not in file.parts:
                try:
                    with open(file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        
                    lines = content.splitlines()
                    for idx, line in enumerate(lines):
                        # Skip comment lines
                        if line.strip().startswith("#") or line.strip().startswith("//"):
                            continue
                            
                        # Scan secrets
                        for name, pattern in secret_patterns.items():
                            if re.search(pattern, line):
                                findings.append({
                                    "file": str(file.relative_to(WORKSPACE)),
                                    "line": idx + 1,
                                    "category": "Exposed Credential",
                                    "severity": "CRITICAL",
                                    "detail": f"Potential {name} match: '{line.strip()[:60]}...'"
                                })
                                
                        # Scan dangerous functions
                        for name, pattern in dangerous_patterns.items():
                            if re.search(pattern, line):
                                findings.append({
                                    "file": str(file.relative_to(WORKSPACE)),
                                    "line": idx + 1,
                                    "category": "Dangerous API / Command Injection",
                                    "severity": "HIGH",
                                    "detail": f"Dangerous function '{name}': '{line.strip()[:60]}...'"
                                })
                except Exception:
                    pass

        # 3. Check for .env file exposure in .gitignore
        gitignore_path = WORKSPACE.parent / ".gitignore"
        if gitignore_path.exists():
            try:
                with open(gitignore_path, "r") as f:
                    gi_content = f.read()
                if ".env" not in gi_content:
                    findings.append({
                        "file": ".gitignore",
                        "line": 0,
                        "category": "Configuration Exposure",
                        "severity": "MEDIUM",
                        "detail": ".env is not specified in .gitignore, which could lead to accidental credentials leak to repository."
                    })
            except Exception:
                pass
        else:
            findings.append({
                "file": "None",
                "line": 0,
                "category": "Missing Gitignore",
                "severity": "LOW",
                "detail": ".gitignore file is missing in the workspace parent."
            })
            
        if not findings:
            return "### Security Scan Report\n\n**Result:** PASSED\nNo critical security vulnerabilities, hardcoded secrets, or dangerous execution APIs detected in the active workspace."
            
        # Format markdown response
        report = "### 🛡️ Security Scan Report\n\n| File | Line | Category | Severity | Detail |\n| :--- | :--- | :--- | :--- | :--- |\n"
        for f in findings:
            report += f"| `{f['file']}` | {f['line']} | **{f['category']}** | `{f['severity']}` | {f['detail']} |\n"
            
        report += "\n**Summary:** Detected " + str(len(findings)) + " potential vulnerability/vulnerabilities. Please review and secure the codebase."
        return report
    except Exception as e:
        return f"Error executing security scan: {e}"

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
    },
    {
        "name": "web_browse_scroll",
        "description": "Scroll the page in a direction ('up', 'down', 'top', 'bottom') by a specified pixel amount.",
        "arguments": ["direction", "amount"]
    },
    {
        "name": "web_browse_get_text",
        "description": "Retrieve the visible innerText of the current page to analyze content, headers, paragraphs, and details.",
        "arguments": []
    },
    {
        "name": "web_browse_set_viewport",
        "description": "Set the browser window/viewport size and optionally emulate mobile device mode.",
        "arguments": ["width", "height", "is_mobile"]
    },
    {
        "name": "web_browse_evaluate",
        "description": "Evaluate custom JavaScript in the context of the page and return the result.",
        "arguments": ["javascript"]
    },
    {
        "name": "security_check",
        "description": "Scan the workspace for potential security issues (exposed credentials, dangerous functions, file exposures).",
        "arguments": []
    }
]
