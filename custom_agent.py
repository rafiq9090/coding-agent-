#!/usr/bin/env python3
"""
Custom Unrestricted Terminal AI Coding Agent.
Entry point file - Bootstrap module.
"""

import sys
import re
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load variables from the agent's installation folder (.env) so API keys are populated globally
agent_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=agent_dir / ".env")


# Import config first to apply quote-stripping and folder structures
from src.config import config, WORKSPACE, get_resolved_model_id

# Try to import litellm
try:
    import litellm
except ImportError:
    print("Please run: pip install litellm playwright anyio rich python-dotenv")
    sys.exit(1)

from src.ui import console, Panel, Markdown, Prompt, run_settings_menu
from src.tools import (
    tool_read_file,
    tool_write_file,
    tool_edit_file,
    tool_run_command,
    tool_web_screenshot,
    tool_search_codebase,
    tool_web_browse_navigate,
    tool_web_browse_click,
    tool_web_browse_type,
    tool_web_browse_get_elements,
    tool_web_browse_screenshot,
    tool_web_browse_close,
    tool_web_browse_scroll,
    tool_web_browse_get_text,
    tool_web_browse_set_viewport,
    tool_web_browse_evaluate,
    tool_security_check
)
from src.mcp_client import mcp_manager

async def get_dynamic_system_prompt(manager) -> str:
    """Combines native tools, custom skills, and all connected MCP tools dynamically"""
    from src.tools import TOOLS_METADATA, load_custom_skills
    tools_list = list(TOOLS_METADATA)
    
    try:
        custom_skills = load_custom_skills()
        for name, skill in custom_skills.items():
            tools_list.append(skill["metadata"])
    except Exception:
        pass
    
    mcp_tools = await manager.list_all_tools()
    for t in mcp_tools:
        tools_list.append({
            "name": t["name"],
            "description": f"[MCP Tool - Server: {t['server']}] {t['description']}",
            "parameters": t["input_schema"]
        })
        
    persona = config.get("persona", "developer")
    persona_descriptions = {
        "developer": "You are a senior developer AI agent operating on a local codebase. You focus on implementation, coding, bug-fixing, refactoring, and following programming best practices.",
        "qa_tester": "You are a quality assurance (QA) and testing engineer. You focus on quality assurance, writing robust unit/integration tests, validating edge cases, verifying page layouts/stylesheets/errors via screenshots, and identifying/reporting bugs.",
        "orchestrator": "You are a task orchestrator and workflow automation expert. You focus on task decomposition, managing execution flow, coordinating multiple agents/tools, and running custom automated workflows.",
        "database_designer": "You are a database designer and administrator. You focus on data modeling, designing schemas, normalizations, setting up migrations, writing optimal SQL queries, indexing, and optimizing query performance.",
        "architecture_designer": "You are a software architecture designer. You focus on high-level system architecture, designing component boundaries, API contracts, choosing structural patterns, and ensuring clean separation of concerns.",
        "planner": "You are a project planner and product manager. You focus on task planning, creating detailed PRDs, writing step-by-step implementation plans, project roadmap scheduling, estimating milestones, and tracking tasks.",
        "security_engineer": "You are a security engineer AI agent. You focus on securing codebases, identifying/mitigating vulnerabilities, scanning for exposed credentials, auditing dependency/package safety, and validating that best security practices are enforced."
    }
    role_description = persona_descriptions.get(persona, persona_descriptions["developer"])
        
    system_prompt = f"""{role_description}
You operate in a structured plan-execute-verify cycle.

Available Tools:
{json.dumps(tools_list, indent=2)}

CRITICAL INSTRUCTIONS:
1. To invoke any tool, output a Markdown code block with JSON format matching:
```json
{{
  "tool": "tool_name",
  "arguments": {{
     "param1": "value"
  }}
}}
```
2. Write small, targeted file edits using 'edit_file' instead of overwriting whole files.
3. Test your code: if you write a web page, start the server and run 'web_screenshot' to check console errors.
4. If a terminal command returns a traceback error or exit code, repair the code immediately.
5. ONLY invoke tools that are directly required to fulfill the user's explicit request. Do NOT perform proactive, unsolicited audits, codebase scans, or extra checks unless the user specifically asked for them.
6. RESPONSE STYLE:
   - Be extremely concise, direct, and professional.
   - Do NOT write long explanations, conversational remarks, or greetings.
   - Before outputting a tool JSON block, write a single short sentence explaining the plan.
   - Do NOT recap the tool output after execution; immediately output the next action or a single short completion statement.
   - For general conversation, questions, or greetings (e.g., "hello", "how are you"), reply directly with a single concise sentence and do NOT invoke any tools or execute code.
"""
    return system_prompt

async def execute_tool_call(tool_name: str, args: dict, manager) -> str:
    """Dispatches tool calls safely, routing MCP tools dynamically"""
    if tool_name == "read_file":
        return tool_read_file(args.get("path", ""))
    elif tool_name == "write_file":
        return tool_write_file(args.get("path", ""), args.get("content", ""))
    elif tool_name == "edit_file":
        return tool_edit_file(args.get("path", ""), args.get("search_block", ""), args.get("replace_block", ""))
    elif tool_name == "run_command":
        return await tool_run_command(args.get("command", ""))
    elif tool_name == "web_screenshot":
        return await tool_web_screenshot(args.get("url", ""))
    elif tool_name == "search_codebase":
        return tool_search_codebase(args.get("query_text", ""))
    elif tool_name == "web_browse_navigate":
        return await tool_web_browse_navigate(args.get("url", ""))
    elif tool_name == "web_browse_click":
        return await tool_web_browse_click(args.get("selector", ""))
    elif tool_name == "web_browse_type":
        return await tool_web_browse_type(args.get("selector", ""), args.get("text", ""))
    elif tool_name == "web_browse_get_elements":
        return await tool_web_browse_get_elements()
    elif tool_name == "web_browse_screenshot":
        return await tool_web_browse_screenshot()
    elif tool_name == "web_browse_close":
        return await tool_web_browse_close()
    elif tool_name == "web_browse_scroll":
        return await tool_web_browse_scroll(args.get("direction", "down"), int(args.get("amount", 500)))
    elif tool_name == "web_browse_get_text":
        return await tool_web_browse_get_text()
    elif tool_name == "web_browse_set_viewport":
        return await tool_web_browse_set_viewport(int(args.get("width", 1280)), int(args.get("height", 720)), bool(args.get("is_mobile", False)))
    elif tool_name == "web_browse_evaluate":
        return await tool_web_browse_evaluate(args.get("javascript", ""))
    elif tool_name == "security_check":
        return tool_security_check()
    else:
        # Check if it is a dynamically loaded custom skill
        from src.tools import load_custom_skills
        try:
            custom_skills = load_custom_skills()
            if tool_name in custom_skills:
                import inspect
                func = custom_skills[tool_name]["execute"]
                sig = inspect.signature(func)
                
                kwargs = {}
                for param in sig.parameters.values():
                    if param.name in args:
                        kwargs[param.name] = args[param.name]
                    elif param.default is inspect.Parameter.empty:
                        kwargs[param.name] = None
                        
                if inspect.iscoroutinefunction(func):
                    result = await func(**kwargs)
                else:
                    result = func(**kwargs)
                return str(result)
        except Exception as e:
            return f"Error executing custom skill '{tool_name}': {e}"

        if "__" in tool_name:
            return await manager.execute_tool(tool_name, args)
        else:
            return f"Error: Tool '{tool_name}' is not recognized."

def parse_markdown_json(response_text: str):
    """Robust parser to extract json blocks containing action specifications"""
    blocks = re.findall(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if not blocks:
        return None
    try:
        return json.loads(blocks[0].strip())
    except json.JSONDecodeError:
        return None

def clean_markdown_explanation(response_text: str) -> str:
    """Removes the ```json ... ``` blocks from the explanation printed to the user"""
    cleaned = re.sub(r"```json\s*.*?\s*```", "", response_text, flags=re.DOTALL)
    return cleaned.strip()

async def main():
    console.print(Panel(
        "[bold cyan]Custom Terminal Coding Agent[/bold cyan]\n"
        "Same-to-Same cursor/antigravity engine inside the CLI.",
        title="Welcome"
    ))
    
    # Initialize and connect configured MCP servers
    await mcp_manager.connect_servers()
    
    try:
        model_choice = config.get("selected_model", "gemini")
        raw_model_id = config.get("model_details", {}).get(model_choice, "gemini/gemini-1.5-flash")
        model_id = get_resolved_model_id(model_choice, raw_model_id)
        
        console.print(f"\n[green]✓[/green] Model configured to: [bold cyan]{model_choice}[/bold cyan] ({model_id})")
        console.print(f"[dim]Workspace folder: {WORKSPACE}[/dim]")
        console.print("[dim]Tip: Type 'settings' at the prompt to configure model or tool permissions.[/dim]\n")
        
        messages = []
        
        while True:
            try:
                task = console.input("[bold yellow]User > [/bold yellow]")
                cmd = task.strip().lower()
                if cmd in ("exit", "quit"):
                    console.print("[dim]Goodbye![/dim]")
                    break
                if cmd in ("settings", "setting", "config", "setup", "configure", "options", "menu"):
                    await run_settings_menu()
                    model_choice = config.get("selected_model", "gemini")
                    raw_model_id = config.get("model_details", {}).get(model_choice, "gemini/gemini-1.5-flash")
                    model_id = get_resolved_model_id(model_choice, raw_model_id)
                    continue
                    
                messages.append({"role": "user", "content": task})
                
                # Interactive Multi-turn Agent loop
                loop_count = 0
                while True:
                    loop_count += 1
                    if loop_count > 5:
                        console.print("[yellow]Notice: Reached execution limit of 5 tool calls for this turn to prevent runaway loops.[/yellow]")
                        break
                    console.print("\n[bold dim]Agent Thinking...[/bold dim]")
                    
                    try:
                        # Limit history window size to avoid rate limits (TPM limits)
                        active_messages = []
                        max_turns = config.get("max_history_turns", 6)
                        if len(messages) > (max_turns + 1):
                            active_messages.append(messages[0])
                            active_messages.extend(messages[-(max_turns):])
                        else:
                            active_messages = messages
    
                        # Get active model identifier based on selected gateway
                        gateway = config.get("selected_model", "gemini")
                        raw_model_id = config.get("model_details", {}).get(gateway, "gemini/gemini-1.5-flash")
                        active_model_id = get_resolved_model_id(gateway, raw_model_id)
    
                        # Compute dynamic system prompt incorporating all native and MCP tools
                        dynamic_system_prompt = await get_dynamic_system_prompt(mcp_manager)
    
                        reply = litellm.completion(
                            model=active_model_id,
                            messages=[{"role": "system", "content": dynamic_system_prompt}] + active_messages,
                            api_base="http://localhost:11434" if gateway == "local" else None,
                            temperature=config.get("temperature", 0.15)
                        ).choices[0].message.content
                    except Exception as e:
                        console.print(f"[bold red]API Error:[/bold red] {e}")
                        if "429" in str(e) or "limit" in str(e).lower() or "quota" in str(e).lower():
                            console.print("[yellow]Tip: You seem to have hit a rate limit or quota limit. Type 'settings' to configure or switch models/gateways.[/yellow]")
                        break
                    
                    explanation = clean_markdown_explanation(reply)
                    if explanation:
                        console.print(Panel(Markdown(explanation), title="Agent Response"))
                    messages.append({"role": "assistant", "content": reply})
                    
                    tool_call = parse_markdown_json(reply)
                    if tool_call and "tool" in tool_call:
                        tool_name = tool_call["tool"]
                        args = tool_call.get("arguments", {})
                        
                        args_str = ", ".join(f"{k}={json.dumps(v)}" for k, v in args.items())
                        console.print(f"[bold green]▶ Tool Call Detected:[/bold green] [cyan]{tool_name}({args_str})[/cyan]")
                        result = await execute_tool_call(tool_name, args, mcp_manager)
                        
                        console.print(Panel(result, title=f"Execution Outcome: {tool_name}"))
                        messages.append({"role": "user", "content": f"Execution Result:\n{result}"})
                    else:
                        break
                        
            except KeyboardInterrupt:
                console.print("\n[dim]Interrupted. Type exit to quit.[/dim]")
            except Exception as e:
                console.print(f"[bold red]Error in loop:[/bold red] {e}")
    finally:
        await mcp_manager.disconnect_all()
        try:
            from src.tools import persistent_shell
            await persistent_shell.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        console.print("\n[dim]Agent terminated.[/dim]")
        sys.exit(0)

