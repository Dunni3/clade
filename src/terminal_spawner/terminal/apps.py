"""Terminal application abstractions for cross-platform support."""

from typing import Protocol


def _escape_for_applescript(s: str) -> str:
    """Escape a string for use inside an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


class TerminalApp(Protocol):
    """Protocol for terminal application implementations."""

    name: str

    def generate_open_script(self) -> str:
        """Generate AppleScript to open an empty terminal window."""
        ...

    def generate_command_script(self, command: str) -> str:
        """Generate AppleScript to open a terminal window and run a command."""
        ...


class TerminalDotApp:
    """Terminal.app implementation."""

    name = "terminal"

    def generate_open_script(self) -> str:
        return (
            'tell application "Terminal"\n'
            "    activate\n"
            '    do script ""\n'
            "end tell"
        )

    def generate_command_script(self, command: str) -> str:
        escaped = _escape_for_applescript(command)
        return (
            'tell application "Terminal"\n'
            "    activate\n"
            f'    do script "{escaped}"\n'
            "end tell"
        )


class ITerm2App:
    """iTerm2 implementation."""

    name = "iterm2"

    def generate_open_script(self) -> str:
        return (
            'tell application "iTerm2"\n'
            "    activate\n"
            "    create window with default profile\n"
            "end tell"
        )

    def generate_command_script(self, command: str) -> str:
        escaped = _escape_for_applescript(command)
        return (
            'tell application "iTerm2"\n'
            "    activate\n"
            "    create window with default profile\n"
            "    tell current session of current window\n"
            f'        write text "{escaped}"\n'
            "    end tell\n"
            "end tell"
        )


def get_terminal_app(name: str) -> TerminalApp:
    """Factory function to get a terminal app implementation.

    Args:
        name: Terminal app name ("terminal" or "iterm2")

    Returns:
        TerminalApp implementation

    Raises:
        ValueError: If app name is not recognized
    """
    if name == "terminal":
        return TerminalDotApp()
    elif name == "iterm2":
        return ITerm2App()
    else:
        raise ValueError(f"Unknown terminal app: {name}")
