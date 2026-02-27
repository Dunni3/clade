"""Tool execution dispatch for the conductor agent.

Each tool function receives its arguments as a dict, operates on a MailboxClient
(and optionally EmberClient), and returns a formatted string result.

These functions mirror the logic in the MCP tool wrappers but are decoupled from
the MCP server framework — both MCP servers and the Anthropic API agent share
the same underlying MailboxClient and EmberClient.
"""

from __future__ import annotations

import logging
import os

from ..communication.mailbox_client import MailboxClient
from ..utils.timestamp import format_timestamp
from ..worker.client import EmberClient

logger = logging.getLogger(__name__)

COLUMNS = ("backlog", "todo", "in_progress", "done", "archived")
PRIORITIES = ("low", "normal", "high", "urgent")


class ToolExecutor:
    """Dispatches tool calls to MailboxClient/EmberClient methods.

    Holds references to the shared clients and worker registry, providing
    a single execute(name, input) entry point for the agent loop.
    """

    def __init__(
        self,
        mailbox: MailboxClient,
        worker_registry: dict[str, dict],
        mailbox_name: str | None = None,
    ):
        self.mailbox = mailbox
        self.worker_registry = worker_registry
        self.mailbox_name = mailbox_name

    def _get_ember_client(self, brother: str) -> EmberClient | None:
        worker = self.worker_registry.get(brother)
        if not worker:
            return None
        url = worker.get("ember_url")
        key = worker.get("ember_api_key") or worker.get("api_key")
        if not url or not key:
            return None
        return EmberClient(url, key, verify_ssl=False)

    async def execute(self, name: str, tool_input: dict) -> str:
        """Execute a tool by name with the given input dict.

        Returns a formatted string result suitable for passing back
        to the Anthropic API as a tool_result.
        """
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"Unknown tool: {name}"
        try:
            return await handler(tool_input)
        except Exception as e:
            logger.exception("Tool '%s' raised an exception", name)
            return f"Error executing {name}: {e}"

    # ---- Task Delegation ----

    async def _tool_delegate_task(self, inp: dict) -> str:
        brother = inp["brother"]
        prompt = inp["prompt"]
        subject = inp.get("subject", "")
        parent_task_id = inp.get("parent_task_id")
        working_dir = inp.get("working_dir")
        max_turns = inp.get("max_turns")
        card_id = inp.get("card_id")
        metadata = inp.get("metadata")
        on_complete = inp.get("on_complete")
        blocked_by_task_id = inp.get("blocked_by_task_id")
        target_branch = inp.get("target_branch")
        project = inp.get("project")

        if brother not in self.worker_registry:
            available = ", ".join(self.worker_registry.keys()) or "(none)"
            return f"Unknown worker '{brother}'. Available workers: {available}"

        worker = self.worker_registry[brother]
        ember = self._get_ember_client(brother)
        if ember is None:
            return f"Worker '{brother}' has no Ember configured."

        # Auto-link parent from env if not explicitly provided
        if parent_task_id is None:
            trigger_id = os.environ.get("TRIGGER_TASK_ID", "")
            if trigger_id:
                try:
                    parent_task_id = int(trigger_id)
                except (ValueError, TypeError):
                    pass

        # Create task in Hearth
        try:
            task_result = await self.mailbox.create_task(
                assignee=brother,
                prompt=prompt,
                subject=subject,
                parent_task_id=parent_task_id,
                metadata=metadata,
                on_complete=on_complete,
                blocked_by_task_id=blocked_by_task_id,
                max_turns=max_turns,
                project=project,
            )
            task_id = task_result["id"]
        except Exception as e:
            return f"Error creating task in Hearth: {e}"

        # Link task to card
        if card_id is not None:
            try:
                await self.mailbox.add_card_link(card_id, "task", str(task_id))
            except Exception:
                pass

        # Check if task is blocked
        actual_blocked_by = task_result.get("blocked_by_task_id")
        if actual_blocked_by is not None:
            lines = [
                f"Task #{task_id} created (deferred — blocked by #{actual_blocked_by}).",
                f"  Subject: {subject or '(none)'}",
                f"  Assignee: {brother}",
                f"  Status: pending (waiting for #{actual_blocked_by} to complete)",
            ]
            if card_id is not None:
                lines.append(f"  Linked to card: #{card_id}")
            return "\n".join(lines)

        # Resolve working_dir
        wd = working_dir
        if wd is None and project:
            project_dirs = worker.get("projects") or {}
            wd = project_dirs.get(project)
        if wd is None:
            wd = worker.get("working_dir")

        try:
            ember_result = await ember.execute_task(
                prompt=prompt,
                subject=subject,
                task_id=task_id,
                working_dir=wd,
                max_turns=max_turns,
                hearth_url=None,
                hearth_api_key=worker.get("hearth_api_key") or worker.get("api_key"),
                hearth_name=brother,
                sender_name=self.mailbox_name,
                target_branch=target_branch,
            )
        except Exception as e:
            try:
                await self.mailbox.update_task(task_id, status="failed", output=f"Ember delegation failed: {e}")
            except Exception as status_err:
                return (
                    f"Task #{task_id} created but Ember delegation failed: {e}\n"
                    f"WARNING: Failed to mark task as failed ({status_err}) — task is orphaned in pending status."
                )
            return f"Task #{task_id} created but Ember delegation failed: {e}"

        try:
            await self.mailbox.update_task(task_id, status="launched")
        except Exception as e:
            logger.error("Task #%d may be orphaned: launched but status update failed: %s", task_id, e)

        session = ember_result.get("session_name", "?")
        lines = [
            f"Task #{task_id} delegated to {brother}.",
            f"  Subject: {subject or '(none)'}",
            f"  Session: {session}",
            f"  Status: launched",
        ]
        if card_id is not None:
            lines.append(f"  Linked to card: #{card_id}")
        return "\n".join(lines)

    async def _tool_check_worker_health(self, inp: dict) -> str:
        brother = inp.get("brother")
        workers = (
            {brother: self.worker_registry[brother]}
            if brother and brother in self.worker_registry
            else self.worker_registry
        )
        if brother and brother not in self.worker_registry:
            return f"Unknown worker '{brother}'."
        if not workers:
            return "No workers configured."

        lines = []
        for name, _config in workers.items():
            ember = self._get_ember_client(name)
            if ember is None:
                lines.append(f"{name}: No Ember configured")
                continue
            try:
                result = await ember.health()
                lines.append(
                    f"{name}: Healthy\n"
                    f"  Active tasks: {result.get('active_tasks', '?')}\n"
                    f"  Uptime: {result.get('uptime_seconds', '?')}s"
                )
            except Exception as e:
                lines.append(f"{name}: Unreachable ({e})")
        return "\n\n".join(lines)

    async def _tool_list_worker_tasks(self, inp: dict) -> str:
        brother = inp.get("brother")
        workers = (
            {brother: self.worker_registry[brother]}
            if brother and brother in self.worker_registry
            else self.worker_registry
        )
        if brother and brother not in self.worker_registry:
            return f"Unknown worker '{brother}'."
        if not workers:
            return "No workers configured."

        lines = []
        for name, _config in workers.items():
            ember = self._get_ember_client(name)
            if ember is None:
                lines.append(f"{name}: No Ember configured")
                continue
            try:
                result = await ember.active_tasks()
                aspens = result.get("aspens")
                if aspens is None:
                    active = result.get("active_task")
                    aspens = [active] if active else []
                if aspens:
                    n = len(aspens)
                    lines.append(f"{name}: {n} active aspen{'s' if n != 1 else ''}")
                    for a in aspens:
                        lines.append(
                            f"  - Task ID: {a.get('task_id', 'N/A')}\n"
                            f"    Subject: {a.get('subject', '(none)')}\n"
                            f"    Session: {a.get('session_name', '?')}"
                        )
                else:
                    lines.append(f"{name}: Idle")
            except Exception as e:
                lines.append(f"{name}: Unreachable ({e})")
        return "\n\n".join(lines)

    # ---- Messaging ----

    async def _tool_send_message(self, inp: dict) -> str:
        recipients = inp["recipients"]
        body = inp["body"]
        subject = inp.get("subject", "")
        task_id = inp.get("task_id")
        result = await self.mailbox.send_message(recipients, body, subject, task_id=task_id)
        names = ", ".join(recipients)
        return f"Message sent to {names} (id: {result['id']})"

    async def _tool_check_mailbox(self, inp: dict) -> str:
        unread_only = inp.get("unread_only", True)
        limit = inp.get("limit", 20)
        messages = await self.mailbox.check_mailbox(unread_only, limit)
        if not messages:
            return "No messages." if not unread_only else "No unread messages."
        lines = []
        for msg in messages:
            read_marker = "" if msg["is_read"] else " [NEW]"
            subj = msg["subject"] or "(no subject)"
            lines.append(
                f"#{msg['id']}{read_marker} from {msg['sender']}: {subj}\n"
                f"  {msg['body'][:100]}{'...' if len(msg['body']) > 100 else ''}\n"
                f"  ({format_timestamp(msg['created_at'])})"
            )
        return "\n\n".join(lines)

    async def _tool_read_message(self, inp: dict) -> str:
        msg = await self.mailbox.read_message(inp["message_id"])
        recipients = ", ".join(msg["recipients"])
        subj = msg["subject"] or "(no subject)"
        lines = [
            f"Message #{msg['id']}",
            f"From: {msg['sender']}",
            f"To: {recipients}",
            f"Subject: {subj}",
            f"Date: {format_timestamp(msg['created_at'])}",
        ]
        if msg.get("read_by"):
            names = ", ".join(r["brother"] for r in msg["read_by"])
            lines.append(f"Read by: {names}")
        lines.append(f"\n{msg['body']}")
        return "\n".join(lines)

    # ---- Tasks ----

    async def _tool_list_tasks(self, inp: dict) -> str:
        tasks = await self.mailbox.get_tasks(
            assignee=inp.get("assignee"),
            status=inp.get("status"),
            limit=inp.get("limit", 20),
        )
        if not tasks:
            return "No tasks found."
        lines = []
        for t in tasks:
            status_str = t["status"]
            if t.get("blocked_by_task_id") and t["status"] == "pending":
                status_str = f"blocked by #{t['blocked_by_task_id']}"
            line = (
                f"#{t['id']} [{status_str}] {t['subject'] or '(no subject)'}\n"
                f"  Assignee: {t['assignee']} | Creator: {t['creator']}\n"
                f"  Created: {format_timestamp(t['created_at'])}"
            )
            if t.get("completed_at"):
                line += f"\n  Completed: {format_timestamp(t['completed_at'])}"
            lines.append(line)
        return "\n\n".join(lines)

    async def _tool_get_task(self, inp: dict) -> str:
        t = await self.mailbox.get_task(inp["task_id"])
        lines = [
            f"Task #{t['id']}",
            f"Status: {t['status']}",
            f"Subject: {t['subject'] or '(no subject)'}",
            f"Assignee: {t['assignee']}",
            f"Creator: {t['creator']}",
            f"Created: {format_timestamp(t['created_at'])}",
        ]
        if t.get("completed_at"):
            lines.append(f"Completed: {format_timestamp(t['completed_at'])}")
        if t.get("parent_task_id"):
            lines.append(f"Parent task: #{t['parent_task_id']}")
        if t.get("root_task_id"):
            lines.append(f"Root task: #{t['root_task_id']}")
        if t.get("blocked_by_task_id"):
            lines.append(f"Blocked by: #{t['blocked_by_task_id']}")
        if t.get("host"):
            lines.append(f"Host: {t['host']}")
        if t.get("session_name"):
            lines.append(f"Session: {t['session_name']}")
        if t.get("working_dir"):
            lines.append(f"Working dir: {t['working_dir']}")
        if t.get("on_complete"):
            lines.append(f"On complete: {t['on_complete']}")
        if t.get("metadata"):
            lines.append(f"Metadata: {t['metadata']}")
        linked_cards = t.get("linked_cards", [])
        if linked_cards:
            lines.append(f"\nLinked cards ({len(linked_cards)}):")
            for card in linked_cards:
                lines.append(f"  Card #{card['id']}: {card['title']} [{card['col']}]")
        children = t.get("children", [])
        if children:
            lines.append(f"\nChildren ({len(children)}):")
            for c in children:
                blocked_suffix = f" (blocked by #{c['blocked_by_task_id']})" if c.get("blocked_by_task_id") else ""
                lines.append(
                    f"  #{c['id']} [{c['status']}] {c.get('subject') or '(no subject)'}"
                    f" — {c['assignee']}{blocked_suffix}"
                )
        blocked_tasks = t.get("blocked_tasks", [])
        if blocked_tasks:
            lines.append(f"\nBlocked by this task ({len(blocked_tasks)}):")
            for bt in blocked_tasks:
                lines.append(
                    f"  #{bt['id']} [{bt['status']}] {bt.get('subject') or '(no subject)'}"
                    f" — {bt['assignee']}"
                )
        if t.get("output"):
            lines.append(f"\nOutput: {t['output']}")
        lines.append(f"\nPrompt:\n{t['prompt']}")
        return "\n".join(lines)

    async def _tool_update_task(self, inp: dict) -> str:
        result = await self.mailbox.update_task(
            inp["task_id"],
            status=inp.get("status"),
            output=inp.get("output"),
            parent_task_id=inp.get("parent_task_id"),
        )
        lines = [
            f"Task #{result['id']} updated.",
            f"  Status: {result['status']}",
            f"  Assignee: {result['assignee']}",
        ]
        if result.get("parent_task_id"):
            lines.append(f"  Parent: #{result['parent_task_id']}")
        if result.get("root_task_id"):
            lines.append(f"  Root: #{result['root_task_id']}")
        return "\n".join(lines)

    async def _tool_retry_task(self, inp: dict) -> str:
        result = await self.mailbox.retry_task(inp["task_id"])
        return (
            f"Retry task #{result['id']} created.\n"
            f"  Subject: {result.get('subject', '(no subject)')}\n"
            f"  Status: {result['status']}\n"
            f"  Assignee: {result['assignee']}\n"
            f"  Parent: #{result.get('parent_task_id', '?')}"
        )

    async def _tool_kill_task(self, inp: dict) -> str:
        result = await self.mailbox.kill_task(inp["task_id"])
        return (
            f"Task #{result['id']} killed.\n"
            f"  Status: {result['status']}\n"
            f"  Assignee: {result['assignee']}"
        )

    # ---- Morsels ----

    async def _tool_deposit_morsel(self, inp: dict) -> str:
        links = []
        if inp.get("task_id") is not None:
            links.append({"object_type": "task", "object_id": str(inp["task_id"])})
        if inp.get("brother") is not None:
            links.append({"object_type": "brother", "object_id": inp["brother"]})
        if inp.get("card_id") is not None:
            links.append({"object_type": "card", "object_id": str(inp["card_id"])})
        result = await self.mailbox.create_morsel(
            body=inp["body"],
            tags=inp.get("tags"),
            links=links or None,
        )
        return f"Morsel #{result.get('id', '?')} deposited."

    async def _tool_list_morsels(self, inp: dict) -> str:
        object_type = None
        object_id = None
        if inp.get("card_id") is not None:
            object_type = "card"
            object_id = inp["card_id"]
        elif inp.get("task_id") is not None:
            object_type = "task"
            object_id = inp["task_id"]
        morsels = await self.mailbox.get_morsels(
            creator=inp.get("creator"),
            tag=inp.get("tag"),
            object_type=object_type,
            object_id=object_id,
            limit=inp.get("limit", 20),
        )
        if not morsels:
            return "No morsels found."
        lines = []
        for m in morsels:
            tags_str = ", ".join(m.get("tags", []))
            header = f"#{m['id']} by {m['creator']}"
            if tags_str:
                header += f" [{tags_str}]"
            header += f" ({format_timestamp(m['created_at'])})"
            body_preview = m["body"][:120] + ("..." if len(m["body"]) > 120 else "")
            lines.append(f"{header}\n  {body_preview}")
        return "\n\n".join(lines)

    async def _tool_get_morsel(self, inp: dict) -> str:
        m = await self.mailbox.get_morsel(inp["morsel_id"])
        tags_str = ", ".join(m.get("tags", []))
        header = f"Morsel #{m['id']} by {m['creator']}"
        if tags_str:
            header += f" [{tags_str}]"
        header += f" ({format_timestamp(m['created_at'])})"
        lines = [header, "", m["body"]]
        link_list = m.get("links", [])
        if link_list:
            lines.append(f"\nLinks ({len(link_list)}):")
            for link in link_list:
                lines.append(f"  {link['object_type']}:{link['object_id']}")
        return "\n".join(lines)

    # ---- Kanban Board ----

    async def _tool_list_board(self, inp: dict) -> str:
        cards = await self.mailbox.get_cards(
            col=inp.get("col"),
            assignee=inp.get("assignee"),
            label=inp.get("label"),
            include_archived=inp.get("include_archived", False),
            project=inp.get("project"),
        )
        if not cards:
            return "No cards found."
        by_col: dict[str, list[dict]] = {}
        for card in cards:
            by_col.setdefault(card["col"], []).append(card)
        lines = []
        display_order = [c for c in COLUMNS if c in by_col]
        for column in display_order:
            col_cards = by_col[column]
            lines.append(f"## {column.upper().replace('_', ' ')} ({len(col_cards)})")
            for c in col_cards:
                priority_badge = f" [{c['priority']}]" if c["priority"] != "normal" else ""
                assignee_badge = f" @{c['assignee']}" if c.get("assignee") else ""
                labels_str = f" ({', '.join(c.get('labels', []))})" if c.get("labels") else ""
                lines.append(f"  #{c['id']}{priority_badge}{assignee_badge}: {c['title']}{labels_str}")
            lines.append("")
        return "\n".join(lines).rstrip()

    async def _tool_get_card(self, inp: dict) -> str:
        c = await self.mailbox.get_card(inp["card_id"])
        lines = [
            f"Card #{c['id']}: {c['title']}",
            f"Column: {c['col']}",
            f"Priority: {c['priority']}",
            f"Creator: {c['creator']}",
        ]
        if c.get("project"):
            lines.append(f"Project: {c['project']}")
        if c.get("assignee"):
            lines.append(f"Assignee: {c['assignee']}")
        if c.get("labels"):
            lines.append(f"Labels: {', '.join(c['labels'])}")
        lines.append(f"Created: {c['created_at']}")
        lines.append(f"Updated: {c['updated_at']}")
        if c.get("links"):
            link_strs = [f"{l['object_type']} #{l['object_id']}" for l in c["links"]]
            lines.append(f"Links ({len(c['links'])}): {', '.join(link_strs)}")
        if c.get("description"):
            lines.append(f"\n{c['description']}")
        return "\n".join(lines)

    async def _tool_create_card(self, inp: dict) -> str:
        col = inp.get("col", "backlog")
        priority = inp.get("priority", "normal")
        if col not in COLUMNS:
            return f"Invalid column '{col}'. Must be one of: {', '.join(COLUMNS)}"
        if priority not in PRIORITIES:
            return f"Invalid priority '{priority}'. Must be one of: {', '.join(PRIORITIES)}"
        links = inp.get("links")
        if links:
            links = [{"object_type": l["object_type"], "object_id": str(l["object_id"])} for l in links]
        card = await self.mailbox.create_card(
            title=inp["title"],
            description=inp.get("description", ""),
            col=col,
            priority=priority,
            assignee=inp.get("assignee"),
            labels=inp.get("labels"),
            links=links,
            project=inp.get("project"),
        )
        return f"Card #{card['id']} created: {card['title']} [{card['col']}]"

    async def _tool_move_card(self, inp: dict) -> str:
        col = inp["col"]
        if col not in COLUMNS:
            return f"Invalid column '{col}'. Must be one of: {', '.join(COLUMNS)}"
        card = await self.mailbox.update_card(inp["card_id"], col=col)
        return f"Card #{card['id']} moved to {card['col']}."

    async def _tool_update_card(self, inp: dict) -> str:
        card_id = inp["card_id"]
        priority = inp.get("priority")
        if priority is not None and priority not in PRIORITIES:
            return f"Invalid priority '{priority}'. Must be one of: {', '.join(PRIORITIES)}"
        kwargs: dict = {}
        for key in ("title", "description", "priority", "assignee", "labels", "project"):
            if key in inp:
                kwargs[key] = inp[key]
        if "links" in inp:
            links = inp["links"]
            kwargs["links"] = (
                [{"object_type": l["object_type"], "object_id": str(l["object_id"])} for l in links]
                if links
                else links
            )
        card = await self.mailbox.update_card(card_id, **kwargs)
        return f"Card #{card['id']} updated: {card['title']} [{card['col']}]"

    async def _tool_archive_card(self, inp: dict) -> str:
        card = await self.mailbox.archive_card(inp["card_id"])
        return f"Card #{card['id']} archived."

    # ---- Trees ----

    async def _tool_list_trees(self, inp: dict) -> str:
        trees = await self.mailbox.get_trees(limit=inp.get("limit", 20))
        if not trees:
            return "No task trees found."
        lines = []
        for tree in trees:
            root = tree.get("root", tree)
            status_counts = tree.get("status_counts", {})
            counts_str = ", ".join(f"{k}: {v}" for k, v in status_counts.items())
            total = tree.get("total_tasks", "?")
            lines.append(
                f"Tree #{root['id']}: {root.get('subject') or '(no subject)'}\n"
                f"  Root assignee: {root['assignee']} | Tasks: {total}\n"
                f"  Statuses: {counts_str or 'n/a'}"
            )
        return "\n\n".join(lines)

    async def _tool_get_tree(self, inp: dict) -> str:
        root_task_id = inp["root_task_id"]
        tree = await self.mailbox.get_tree(root_task_id)
        lines = [f"Task tree rooted at #{root_task_id}:\n"]

        def _render_node(node: dict, depth: int = 0) -> None:
            indent = "  " * depth
            prefix = "└─ " if depth > 0 else ""
            subject = node.get("subject") or "(no subject)"
            lines.append(
                f"{indent}{prefix}#{node['id']} [{node['status']}] {subject}"
                f" — {node['assignee']}"
            )
            for child in node.get("children", []):
                _render_node(child, depth + 1)

        root = tree.get("root", tree)
        _render_node(root)
        return "\n".join(lines)

    # ---- Search ----

    async def _tool_search(self, inp: dict) -> str:
        result = await self.mailbox.search(
            query=inp["query"],
            types=inp.get("types"),
            limit=inp.get("limit", 20),
            created_after=inp.get("created_after"),
            created_before=inp.get("created_before"),
        )
        results = result.get("results", [])
        if not results:
            return f"No results for '{inp['query']}'."
        lines = [f"Search results for '{inp['query']}' ({len(results)} found):\n"]
        type_badges = {"task": "T", "morsel": "M", "card": "C"}
        for r in results:
            badge = type_badges.get(r["type"], "?")
            snippet = r.get("snippet", "")
            snippet = snippet.replace("<mark>", "**").replace("</mark>", "**")
            meta_parts = []
            if r.get("status"):
                meta_parts.append(r["status"])
            if r.get("col"):
                meta_parts.append(r["col"])
            if r.get("assignee"):
                meta_parts.append(f"@{r['assignee']}")
            if r.get("creator"):
                meta_parts.append(f"by {r['creator']}")
            meta = " | ".join(meta_parts)
            lines.append(
                f"[{badge}] #{r['id']}: {r['title']}\n"
                f"  {snippet}\n"
                f"  {meta}"
            )
        return "\n\n".join(lines)
