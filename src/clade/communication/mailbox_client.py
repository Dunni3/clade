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
        self,
        recipients: list[str],
        body: str,
        subject: str = "",
        task_id: int | None = None,
    ) -> dict:
        payload: dict = {"recipients": recipients, "body": body, "subject": subject}
        if task_id is not None:
            payload["task_id"] = task_id
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                self._url("/messages"),
                json=payload,
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

    async def create_task(
        self,
        assignee: str,
        prompt: str,
        subject: str = "",
        session_name: str | None = None,
        host: str | None = None,
        working_dir: str | None = None,
        parent_task_id: int | None = None,
    ) -> dict:
        payload: dict = {"assignee": assignee, "prompt": prompt, "subject": subject}
        if session_name is not None:
            payload["session_name"] = session_name
        if host is not None:
            payload["host"] = host
        if working_dir is not None:
            payload["working_dir"] = working_dir
        if parent_task_id is not None:
            payload["parent_task_id"] = parent_task_id
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                self._url("/tasks"),
                json=payload,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_tasks(
        self,
        assignee: str | None = None,
        status: str | None = None,
        creator: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        params: dict = {"limit": limit}
        if assignee:
            params["assignee"] = assignee
        if status:
            params["status"] = status
        if creator:
            params["creator"] = creator
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url("/tasks"),
                params=params,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_task(self, task_id: int) -> dict:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url(f"/tasks/{task_id}"),
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    def register_key_sync(self, name: str, key: str) -> bool:
        """Register an API key with the Hearth. Returns True on success.

        Uses synchronous httpx since key registration is a one-shot call
        during CLI onboarding (which is sync).
        """
        resp = httpx.post(
            self._url("/keys"),
            json={"name": name, "key": key},
            headers=self.headers,
            timeout=10,
            verify=self.verify_ssl,
        )
        return resp.status_code in (200, 201, 409)  # 409 = already registered, OK

    async def update_task(
        self,
        task_id: int,
        status: str | None = None,
        output: str | None = None,
    ) -> dict:
        payload: dict = {}
        if status is not None:
            payload["status"] = status
        if output is not None:
            payload["output"] = output
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.patch(
                self._url(f"/tasks/{task_id}"),
                json=payload,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def kill_task(self, task_id: int) -> dict:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                self._url(f"/tasks/{task_id}/kill"),
                headers=self.headers,
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()

    # -- Morsels --

    async def create_morsel(
        self,
        body: str,
        tags: list[str] | None = None,
        links: list[dict] | None = None,
    ) -> dict:
        payload: dict = {"body": body}
        if tags:
            payload["tags"] = tags
        if links:
            payload["links"] = links
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                self._url("/morsels"),
                json=payload,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_morsels(
        self,
        creator: str | None = None,
        tag: str | None = None,
        object_type: str | None = None,
        object_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        params: dict = {"limit": limit, "offset": offset}
        if creator:
            params["creator"] = creator
        if tag:
            params["tag"] = tag
        if object_type:
            params["object_type"] = object_type
        if object_id is not None:
            params["object_id"] = object_id
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url("/morsels"),
                params=params,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_morsel(self, morsel_id: int) -> dict:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url(f"/morsels/{morsel_id}"),
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    # -- Trees --

    async def get_trees(self, limit: int = 50, offset: int = 0) -> list[dict]:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url("/trees"),
                params={"limit": limit, "offset": offset},
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_tree(self, root_id: int) -> dict:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url(f"/trees/{root_id}"),
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    # -- Ember Registration --

    # -- Kanban --

    async def create_card(
        self,
        title: str,
        description: str = "",
        col: str = "backlog",
        priority: str = "normal",
        assignee: str | None = None,
        labels: list[str] | None = None,
        links: list[dict] | None = None,
    ) -> dict:
        payload: dict = {"title": title, "description": description, "col": col, "priority": priority}
        if assignee is not None:
            payload["assignee"] = assignee
        if labels:
            payload["labels"] = labels
        if links:
            payload["links"] = links
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                self._url("/kanban/cards"),
                json=payload,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_cards(
        self,
        col: str | None = None,
        assignee: str | None = None,
        creator: str | None = None,
        priority: str | None = None,
        label: str | None = None,
        include_archived: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        params: dict = {"limit": limit, "offset": offset}
        if col:
            params["col"] = col
        if assignee:
            params["assignee"] = assignee
        if creator:
            params["creator"] = creator
        if priority:
            params["priority"] = priority
        if label:
            params["label"] = label
        if include_archived:
            params["include_archived"] = True
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url("/kanban/cards"),
                params=params,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_card(self, card_id: int) -> dict:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                self._url(f"/kanban/cards/{card_id}"),
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def update_card(
        self,
        card_id: int,
        **kwargs,
    ) -> dict:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.patch(
                self._url(f"/kanban/cards/{card_id}"),
                json=kwargs,
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def archive_card(self, card_id: int) -> dict:
        return await self.update_card(card_id, col="archived")

    async def delete_card(self, card_id: int) -> bool:
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.delete(
                self._url(f"/kanban/cards/{card_id}"),
                headers=self.headers,
                timeout=10,
            )
            return resp.status_code == 204

    # -- Ember Registration --

    def register_ember_sync(self, name: str, ember_url: str) -> bool:
        """Register an Ember server with the Hearth. Returns True on success.

        Uses synchronous httpx since ember registration is a one-shot call
        during CLI setup (which is sync).
        """
        resp = httpx.put(
            self._url(f"/embers/{name}"),
            json={"ember_url": ember_url},
            headers=self.headers,
            timeout=10,
            verify=self.verify_ssl,
        )
        return resp.status_code in (200, 201)

