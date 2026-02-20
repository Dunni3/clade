"""HTTP client for the Ember server API."""

from __future__ import annotations

import httpx


class EmberClient:
    """Thin wrapper around the Ember REST API."""

    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.verify_ssl = verify_ssl

    async def health(self) -> dict:
        """Check Ember health — no auth needed."""
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                f"{self.base_url}/health",
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def execute_task(
        self,
        prompt: str,
        subject: str = "",
        task_id: int | None = None,
        working_dir: str | None = None,
        max_turns: int = 50,
        hearth_url: str | None = None,
        hearth_api_key: str | None = None,
        hearth_name: str | None = None,
        sender_name: str | None = None,
    ) -> dict:
        """Submit a task for execution."""
        payload: dict = {
            "prompt": prompt,
            "subject": subject,
            "max_turns": max_turns,
        }
        if task_id is not None:
            payload["task_id"] = task_id
        if working_dir is not None:
            payload["working_dir"] = working_dir
        if hearth_url is not None:
            payload["hearth_url"] = hearth_url
        if hearth_api_key is not None:
            payload["hearth_api_key"] = hearth_api_key
        if hearth_name is not None:
            payload["hearth_name"] = hearth_name
        if sender_name is not None:
            payload["sender_name"] = sender_name

        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                f"{self.base_url}/tasks/execute",
                json=payload,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def active_tasks(self) -> dict:
        """Get active task info and orphaned sessions."""
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                f"{self.base_url}/tasks/active",
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
