import subprocess


def generate_applescript(command: str | None = None, app: str = "iterm2") -> str:
    if app == "iterm2":
        if command:
            return (
                'tell application "iTerm2"\n'
                "    activate\n"
                "    create window with default profile\n"
                "    tell current session of current window\n"
                f'        write text "{command}"\n'
                "    end tell\n"
                "end tell"
            )
        else:
            return (
                'tell application "iTerm2"\n'
                "    activate\n"
                "    create window with default profile\n"
                "end tell"
            )
    elif app == "terminal":
        if command:
            return (
                'tell application "Terminal"\n'
                "    activate\n"
                f'    do script "{command}"\n'
                "end tell"
            )
        else:
            return (
                'tell application "Terminal"\n'
                "    activate\n"
                '    do script ""\n'
                "end tell"
            )
    else:
        raise ValueError(f"Unknown terminal app: {app}")


def run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return "OK"
