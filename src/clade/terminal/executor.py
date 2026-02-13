"""Execute AppleScript via osascript."""
import subprocess


def run_applescript(script: str) -> str:
    """Execute AppleScript code via osascript.

    Args:
        script: AppleScript source code to execute

    Returns:
        "OK" on success, or "Error: <message>" on failure
    """
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return "OK"
