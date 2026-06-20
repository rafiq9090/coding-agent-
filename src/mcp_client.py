import os
import sys
import json
import asyncio
from typing import Dict, List, Any
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.config import config
from src.ui import console

class MCPManager:
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = None

    async def connect_servers(self):
        """Connects to all configured MCP servers defined in settings."""
        mcp_configs = config.get("mcp_servers", {})
        if not mcp_configs:
            return

        self.exit_stack = AsyncExitStack()
        console.print("[dim]Connecting to MCP servers...[/dim]")
        for name, cfg in mcp_configs.items():
            if not isinstance(cfg, dict) or "command" not in cfg:
                continue
            
            command = cfg["command"]
            args = cfg.get("args", [])
            env = os.environ.copy()
            if cfg.get("env"):
                env.update(cfg["env"])

            try:
                params = StdioServerParameters(
                    command=command,
                    args=args,
                    env=env
                )
                
                transport = stdio_client(params)
                read, write = await self.exit_stack.enter_async_context(transport)
                
                session = ClientSession(read, write)
                await self.exit_stack.enter_async_context(session)
                await session.initialize()
                
                self.sessions[name] = session
                console.print(f"[green]✓[/green] MCP server connected: [bold cyan]{name}[/bold cyan]")
            except Exception as e:
                console.print(f"[bold red]✗ Failed to connect MCP server '{name}':[/bold red] {e}")

    async def list_all_tools(self) -> List[Dict[str, Any]]:
        """Aggregates all tools from all connected MCP servers."""
        all_tools = []
        for server_name, session in self.sessions.items():
            try:
                tools_response = await session.list_tools()
                for tool in tools_response.tools:
                    # Combined name is format: servername__toolname
                    combined_name = f"{server_name}__{tool.name}"
                    all_tools.append({
                        "server": server_name,
                        "original_name": tool.name,
                        "name": combined_name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema
                    })
            except Exception as e:
                console.print(f"[bold red]Failed listing tools for '{server_name}':[/bold red] {e}")
        return all_tools

    async def execute_tool(self, combined_name: str, arguments: dict) -> str:
        """Executes a tool on the target MCP server using combined name."""
        if "__" not in combined_name:
            return f"Error: Tool name '{combined_name}' must be formatted as 'server__toolname'"
            
        server_name, tool_name = combined_name.split("__", 1)
        session = self.sessions.get(server_name)
        if not session:
            return f"Error: MCP Server '{server_name}' is not connected."

        try:
            result = await session.call_tool(tool_name, arguments)
            contents = []
            for item in result.content:
                if hasattr(item, "text"):
                    contents.append(item.text)
                elif isinstance(item, dict) and "text" in item:
                    contents.append(item["text"])
                else:
                    contents.append(str(item))
            return "\n".join(contents)
        except Exception as e:
            return f"Error executing tool '{tool_name}' on '{server_name}': {e}"

    async def disconnect_all(self):
        """Disconnects all MCP servers cleanly."""
        if self.exit_stack:
            try:
                await self.exit_stack.aclose()
            except Exception:
                pass
        self.sessions.clear()
        self.exit_stack = None

# Global manager instance
mcp_manager = MCPManager()
