"""SSH task delegation MCP tool definitions."""

import os

from mcp.server.fastmcp import FastMCP

from ...communication.mailbox_client import MailboxClient
from ...core.config import load_config
from ...tasks.ssh_task import TaskResult, generate_session_name, initiate_task, wrap_prompt


_NOT_CONFIGURED = "Hearth not configured. Set HEARTH_URL and HEARTH_API_KEY env vars."


def create_task_tools(
    mcp: FastMCP,
    mailbox: MailboxClient | None,
    config: dict | None = None,
    mailbox_url: str | None = None,
    mailbox_api_key: str | None = None,
) -> dict:
    """Register task delegation tools with an MCP server.

    Args:
        mcp: FastMCP server instance to register tools with
        mailbox: MailboxClient instance, or None if not configured
        config: Terminal spawner config (for brother definitions). If None, loads from default.
        mailbox_url: Mailbox API URL (passed to remote task for hook-based logging)
        mailbox_api_key: Mailbox API key (passed to remote task for hook-based logging)
    """
    if config is None:
        config = load_config()

    brothers = config.get("brothers", {})
    mailbox_name = os.environ.get("HEARTH_NAME") or os.environ.get("MAILBOX_NAME")

    @mcp.tool()
    async def initiate_ssh_task(
        brother: str,
        prompt: str,
        subject: str = "",
        working_dir: str | None = None,
        max_turns: int | None = None,
        auto_pull: bool = False,
    ) -> str:
        """Send a task to a brother via SSH. Launches Claude Code in a detached tmux session.

        The brother will receive the prompt, do the work, and report back via the mailbox.
        Tasks are tracked in the mailbox database.

        WARNING: The remote Claude session runs with --dangerously-skip-permissions by default.
        This gives the brother full autonomous control — it can read/write/delete files and run
        arbitrary commands without human approval. Monitor live by attaching to the tmux session
        on the remote host if needed.

        Args:
            brother: Which brother to send the task to — "jerry" or "oppy".
            prompt: The task prompt / instructions for the brother.
            subject: Short description of the task.
            working_dir: Override the brother's default working directory.
            max_turns: Optional maximum Claude turns. If not set, no turn limit is applied.
            auto_pull: If true, git pull the MCP server repo on the remote host before launching. Default true.
        """
        if mailbox is None:
            return _NOT_CONFIGURED

        bro = brothers.get(brother)
        if not bro:
            return f"Unknown brother: {brother}. Available: {', '.join(brothers.keys())}"

        host = bro["host"]
        wd = working_dir or bro.get("working_dir")
        session_name = generate_session_name(brother, subject)

        # 1. Create task record in mailbox
        try:
            task_resp = await mailbox.create_task(
                assignee=brother,
                prompt=prompt,
                subject=subject,
                session_name=session_name,
                host=host,
                working_dir=wd,
            )
            task_id = task_resp["id"]
        except Exception as e:
            return f"Error creating task record: {e}"

        # 2. Wrap prompt with task context
        sender = mailbox_name or "doot"
        full_prompt = wrap_prompt(prompt, brother, subject, task_id, sender)

        # 3. Launch via SSH (pass mailbox credentials for hook-based task logging)
        result: TaskResult = initiate_task(
            host=host,
            working_dir=wd,
            prompt=full_prompt,
            session_name=session_name,
            max_turns=max_turns,
            auto_pull=auto_pull,
            task_id=task_id,
            mailbox_url=mailbox_url,
            mailbox_api_key=mailbox_api_key,
        )

        # 4. Update task status based on result
        if not result.success:
            try:
                await mailbox.update_task(task_id, status="failed", output=result.message)
            except Exception:
                pass
            error_detail = result.message
            if result.stderr:
                error_detail += f"\nstderr: {result.stderr}"
            return f"Task #{task_id} failed to launch: {error_detail}"

        try:
            await mailbox.update_task(task_id, status="launched")
        except Exception:
            pass

        return (
            f"Task #{task_id} launched successfully.\n"
            f"  Brother: {brother}\n"
            f"  Host: {host}\n"
            f"  Session: {session_name}\n"
            f"  Subject: {subject or '(none)'}\n"
            f"Brother {brother} will report back via the mailbox."
        )

    return {
        "initiate_ssh_task": initiate_ssh_task,
    }
