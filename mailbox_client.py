"""HTTP client for the brother mailbox API."""

from __future__ import annotations

import httpx


class MailboxClient:
    """Thin wrapper around the mailbox REST API."""

    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.verify_ssl = verify_ssl

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    async def send_message(
        self, recipients: list[str], body: str, subject: str = ""
    ) -> dict:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                self._url("/messages"),
                json={"recipients": recipients, "body": body, "subject": subject},
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def check_mailbox(
        self, unread_only: bool = True, limit: int = 20
    ) -> list[dict]:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url("/messages"),
                params={"unread_only": unread_only, "limit": limit},
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def read_message(self, message_id: int) -> dict:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            # Get full message detail
            resp = await client.get(
                self._url(f"/messages/{message_id}"),
                headers=self.headers,
                timeout=10,
            )

            # If 404 (not a recipient), fall back to view endpoint
            if resp.status_code == 404:
                return await self.view_message(message_id)

            resp.raise_for_status()
            msg = resp.json()

            # Auto-mark as read (ignore 404 if already read)
            try:
                await client.post(
                    self._url(f"/messages/{message_id}/read"),
                    headers=self.headers,
                    timeout=10,
                )
            except httpx.HTTPStatusError:
                pass

            return msg

    async def browse_feed(
        self,
        *,
        sender: str | None = None,
        recipient: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        params: dict = {"limit": limit, "offset": offset}
        if sender:
            params["sender"] = sender
        if recipient:
            params["recipient"] = recipient
        if query:
            params["q"] = query
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url("/messages/feed"),
                params=params,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def view_message(self, message_id: int) -> dict:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                self._url(f"/messages/{message_id}/view"),
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def unread_count(self) -> int:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url("/unread"),
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["unread"]
