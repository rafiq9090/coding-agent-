# Example custom skill file.
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
