"""
Personal AI coding agent built on the Claude Agent SDK.
Gives Claude: file read/write/edit, terminal (Bash), and a custom
browser_test tool (via Playwright) to visually verify web apps it builds.
"""

import anyio
from pathlib import Path
from claude_agent_sdk import (
    query,
    tool,
    create_sdk_mcp_server,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    AssistantMessage,
    TextBlock,
    HookMatcher,
)

# ---------------------------------------------------------------------
# Custom tool: open a URL in a real browser, screenshot it, report errors
# ---------------------------------------------------------------------
@tool(
    "browser_test",
    "Open a URL in a real Chromium browser, wait for it to load, take a "
    "full-page screenshot, and report any JavaScript console/page errors. "
    "Use this after building or changing a web app to visually confirm it "
    "actually works, not just that the code compiles.",
    {"url": str},
)
async def browser_test(args):
    from playwright.async_api import async_playwright

    url = args["url"]
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
        except Exception as e:
            await browser.close()
            return {"content": [{"type": "text", "text": f"Failed to load {url}: {e}"}]}

        screenshot_path = str(Path("./screenshot.png").resolve())
        await page.screenshot(path=screenshot_path, full_page=True)
        title = await page.title()
        await browser.close()

    error_text = "\n".join(errors) if errors else "No console/page errors detected."
    return {
        "content": [{
            "type": "text",
            "text": f"Loaded '{title}' at {url}.\nConsole errors:\n{error_text}\n"
                    f"Screenshot saved to {screenshot_path}",
        }]
    }


browser_server = create_sdk_mcp_server(name="browser", version="1.0.0", tools=[browser_test])


# ---------------------------------------------------------------------
# Safety hook: block obviously destructive shell commands before they run
# ---------------------------------------------------------------------
async def guard_bash(input_data, tool_use_id, context):
    if input_data["tool_name"] != "Bash":
        return {}
    command = input_data["tool_input"].get("command", "")
    blocked = ["rm -rf /", "rm -rf ~", ":(){:|:&};:", "mkfs", "> /dev/sda", "shutdown", "del /f /s /q C:\\"]
    for pattern in blocked:
        if pattern in command:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Blocked dangerous pattern: {pattern}",
                }
            }
    return {}


async def main():
    # Everything Claude touches is scoped to this folder, not your whole PC.
    workspace = Path("./agent_workspace").resolve()
    workspace.mkdir(exist_ok=True)

    options = ClaudeAgentOptions(
        cwd=str(workspace),
        system_prompt=(
            "You are an autonomous coding agent. Plan before editing, write code, "
            "create projects, run tests and terminal commands, and use browser_test "
            "to visually confirm web apps actually render and run without console "
            "errors before declaring a task finished. Explain risky commands before "
            "running them."
        ),
        mcp_servers={"browser": browser_server},
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "mcp__browser__browser_test"],
        permission_mode="acceptEdits",  # auto-approve file edits; Bash still goes through the hook
        hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[guard_bash])]},
        max_turns=200,
    )

    print(f"Workspace: {workspace}")
    print("Describe a task (or type 'quit'):")

    async with ClaudeSDKClient(options=options) as client:
        while True:
            task = input("\n> ")
            if task.strip().lower() in ("quit", "exit"):
                break
            await client.query(task)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            print(block.text)


if __name__ == "__main__":
    anyio.run(main)