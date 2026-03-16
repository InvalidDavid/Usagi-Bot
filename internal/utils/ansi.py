BLUE = "\u001b[2;34m"
RED = "\u001b[2;31m"
GREEN = "\u001b[2;32m"
YELLOW = "\u001b[2;33m"
RESET = "\u001b[0m"


def block(text: str, color: str = BLUE) -> str:
    return f"```ansi\n{color}{text}{RESET}```"
