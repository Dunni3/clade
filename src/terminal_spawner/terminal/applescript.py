"""AppleScript generation for spawning terminal windows on macOS."""

from .apps import get_terminal_app


def _escape_for_applescript(s: str) -> str:
    """Escape a string for use inside an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def generate_applescript(command: str | None = None, app: str = "iterm2") -> str:
    """Generate AppleScript to spawn a terminal window.

    Args:
        command: Optional shell command to run in the new window
        app: Terminal application to use ("iterm2" or "terminal")

    Returns:
        AppleScript source code as a string

    Raises:
        ValueError: If app is not recognized
    """
    terminal = get_terminal_app(app)
    if command:
        return terminal.generate_command_script(command)
    else:
        return terminal.generate_open_script()
