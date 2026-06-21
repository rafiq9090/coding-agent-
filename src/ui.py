import sys
from pathlib import Path

# Try to import rich for premium UI styling; fallback to standard print if not installed
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.prompt import Prompt
    from rich.status import Status
    console = Console()
except ImportError:
    class BasicConsole:
        def print(self, text, style=None):
            if isinstance(text, Panel):
                print(f"\n=== {text.title} ===\n{text.renderable}\n=================\n")
            elif isinstance(text, Markdown):
                print(text.markup)
            else:
                print(text)
        def input(self, prompt_text):
            return input(prompt_text)
    console = BasicConsole()
    class Prompt:
        @staticmethod
        def ask(prompt_text, choices=None, default=None):
            choice_str = f" [{'|'.join(choices)}]" if choices else ""
            default_str = f" (default: {default})" if default else ""
            res = input(f"{prompt_text}{choice_str}{default_str}: ").strip()
            return res if res else default
    class Panel:
        def __init__(self, renderable, title="", border_style=""):
            self.renderable = renderable
            self.title = title
    class Markdown:
        def __init__(self, markup):
            self.markup = markup

class Confirm:
    @staticmethod
    def ask(prompt_text) -> bool:
        while True:
            try:
                # Custom input prompts to support quick exits
                res = input(f"{prompt_text} (y/n) [or 'exit' to quit]: ").strip().lower()
                if res in ("exit", "quit"):
                    console.print("[dim]Goodbye![/dim]")
                    sys.exit(0)
                if res in ("y", "yes", "true", "1"):
                    return True
                if res in ("n", "no", "false", "0"):
                    return False
                console.print("[yellow]Please enter y or n, or type 'exit' to quit.[/yellow]")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye![/dim]")
                sys.exit(0)


# Import config helpers
from src.config import config, save_config, WORKSPACE

async def run_settings_menu():
    global config
    while True:
        # Build permissions list block
        perm_lines = []
        for k, v in config.get("permission_policy", {}).items():
            color = "green" if v == "always" else "yellow" if v == "ask" else "red"
            perm_lines.append(f"  • [cyan]{k:18}[/cyan]: [{color}]{v}[/{color}]")
        perm_text = "\n".join(perm_lines)

        gateway = config.get("selected_model", "gemini")
        model_id = config.get("model_details", {}).get(gateway, "gemini/gemini-1.5-flash")
        persona = config.get("persona", "developer")

        console.print(Panel(
            f"[bold white]Current Configuration:[/bold white]\n"
            f"  • [cyan]Model Gateway    [/cyan]: [bold green]{gateway}[/bold green] ({model_id})\n"
            f"  • [cyan]Persona          [/cyan]: [bold green]{persona}[/bold green]\n"
            f"  • [cyan]Temperature      [/cyan]: [bold green]{config.get('temperature')}[/bold green]\n"
            f"  • [cyan]Max History Turns[/cyan]: [bold green]{config.get('max_history_turns')}[/bold green]\n"
            f"  • [cyan]Command Timeout  [/cyan]: [bold green]{config.get('command_timeout')}s[/bold green]\n"
            f"  • [cyan]Allowed Dirs     [/cyan]: [dim]{config.get('allowed_dirs')}[/dim]\n\n"
            f"[bold white]Tool Permissions Policy:[/bold white]\n{perm_text}",
            title="⚙️ Agent Settings Menu",
            border_style="cyan"
        ))
        
        choice = Prompt.ask(
            "Select action",
            choices=["model", "persona", "parameters", "permissions", "allowed_dirs", "back"],
            default="back"
        )
        
        if choice == "back":
            break
        elif choice == "model":
            model_choice = Prompt.ask(
                "Select Model Gateway",
                choices=["gemini", "claude", "groq", "local"],
                default=gateway
            )
            config["selected_model"] = model_choice
            
            # Allow changing the specific model ID
            current_id = config.get("model_details", {}).get(model_choice, "")
            new_id = Prompt.ask(
                f"Enter specific model ID for {model_choice}",
                default=current_id
            )
            if "model_details" not in config:
                config["model_details"] = {}
            config["model_details"][model_choice] = new_id
            save_config(config)
            console.print(f"[green]✓[/green] Model configured to: [bold cyan]{new_id}[/bold cyan]\n")
            
        elif choice == "persona":
            persona_choice = Prompt.ask(
                "Select Agent Persona",
                choices=["developer", "qa_tester", "orchestrator", "database_designer", "architecture_designer", "planner"],
                default=persona
            )
            config["persona"] = persona_choice
            save_config(config)
            console.print(f"[green]✓[/green] Persona configured to: [bold cyan]{persona_choice}[/bold cyan]\n")

        elif choice == "parameters":
            param = Prompt.ask(
                "Select parameter to configure",
                choices=["temperature", "max_history_turns", "command_timeout", "cancel"],
                default="cancel"
            )
            if param == "temperature":
                try:
                    val = float(Prompt.ask("Enter Temperature (0.0 to 1.0)", default=str(config.get("temperature", 0.15))))
                    config["temperature"] = max(0.0, min(val, 2.0))
                    save_config(config)
                    console.print(f"[green]✓[/green] Temperature updated to {config['temperature']}\n")
                except ValueError:
                    console.print("[red]Invalid float value.[/red]\n")
            elif param == "max_history_turns":
                try:
                    val = int(Prompt.ask("Enter max history turns to retain", default=str(config.get("max_history_turns", 6))))
                    config["max_history_turns"] = max(1, val)
                    save_config(config)
                    console.print(f"[green]✓[/green] Max history turns updated to {config['max_history_turns']}\n")
                except ValueError:
                    console.print("[red]Invalid integer value.[/red]\n")
            elif param == "command_timeout":
                try:
                    val = int(Prompt.ask("Enter command execution timeout in seconds", default=str(config.get("command_timeout", 45))))
                    config["command_timeout"] = max(1, val)
                    save_config(config)
                    console.print(f"[green]✓[/green] Command timeout updated to {config['command_timeout']}s\n")
                except ValueError:
                    console.print("[red]Invalid integer value.[/red]\n")
                    
        elif choice == "permissions":
            tools = list(config.get("permission_policy", {}).keys())
            tool_choice = Prompt.ask(
                "Select tool to configure",
                choices=tools + ["cancel"],
                default="cancel"
            )
            if tool_choice != "cancel":
                policy_choice = Prompt.ask(
                    f"Set permission policy for '{tool_choice}'",
                    choices=["always", "ask", "deny"],
                    default="ask"
                )
                config["permission_policy"][tool_choice] = policy_choice
                save_config(config)
                console.print(f"[green]✓[/green] '{tool_choice}' set to: [bold cyan]{policy_choice}[/bold cyan]\n")
                
        elif choice == "allowed_dirs":
            dir_action = Prompt.ask(
                "Modify allowed directories list",
                choices=["add", "remove", "reset", "cancel"],
                default="cancel"
            )
            if dir_action == "add":
                new_path = Prompt.ask("Enter absolute directory path to allow")
                p = Path(new_path).resolve()
                if p.is_dir():
                    if "allowed_dirs" not in config:
                        config["allowed_dirs"] = []
                    if str(p) not in config["allowed_dirs"]:
                        config["allowed_dirs"].append(str(p))
                        save_config(config)
                        console.print(f"[green]✓[/green] Added directory: {p}\n")
                    else:
                        console.print("[yellow]Directory is already in the allowed list.[/yellow]\n")
                else:
                    console.print("[red]Invalid path or directory does not exist.[/red]\n")
            elif dir_action == "remove":
                if not config.get("allowed_dirs"):
                    console.print("[yellow]Allowed list is empty.[/yellow]\n")
                    continue
                rem_path = Prompt.ask(
                    "Select directory to remove",
                    choices=config["allowed_dirs"] + ["cancel"],
                    default="cancel"
                )
                if rem_path != "cancel":
                    config["allowed_dirs"].remove(rem_path)
                    save_config(config)
                    console.print(f"[green]✓[/green] Removed directory: {rem_path}\n")
            elif dir_action == "reset":
                config["allowed_dirs"] = [str(WORKSPACE)]
                save_config(config)
                console.print(f"[green]✓[/green] Reset allowed directories list to defaults.\n")
