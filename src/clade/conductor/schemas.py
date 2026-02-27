"""Anthropic API tool schema definitions for the conductor agent.

Each tool is defined as a dict matching the Anthropic API tool format:
    {"name": str, "description": str, "input_schema": JSONSchema}
"""

TOOLS: list[dict] = [
    # --- Task Delegation ---
    {
        "name": "delegate_task",
        "description": (
            "Delegate a task to a worker brother via their Ember server. "
            "Creates a task in the Hearth, sends it to the worker's Ember, and updates the task status. "
            "If blocked_by_task_id is set, the task is created but not delegated — "
            "it will be auto-delegated when the blocking task completes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "brother": {"type": "string", "description": "Worker name (e.g. 'oppy')."},
                "prompt": {"type": "string", "description": "The task prompt/instructions."},
                "subject": {"type": "string", "description": "Short description of the task."},
                "parent_task_id": {
                    "type": "integer",
                    "description": "Parent task ID for tree linking. Auto-reads from TRIGGER_TASK_ID if not provided.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Override the worker's default working directory.",
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Maximum Claude turns. If not set, no turn limit.",
                },
                "card_id": {
                    "type": "integer",
                    "description": "Kanban card ID to link this task to.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Dict stored on root tasks. Supports keys like 'max_depth'.",
                },
                "on_complete": {
                    "type": "string",
                    "description": "Follow-up instructions for the Conductor when this task completes or fails.",
                },
                "blocked_by_task_id": {
                    "type": "integer",
                    "description": "Task ID that must complete before this task runs.",
                },
                "target_branch": {
                    "type": "string",
                    "description": "Git branch to check out in the worktree.",
                },
                "project": {
                    "type": "string",
                    "description": "Project name (e.g. 'clade', 'omtra'). Resolves working_dir from per-project mapping.",
                },
            },
            "required": ["brother", "prompt"],
        },
    },
    {
        "name": "check_worker_health",
        "description": "Check the health of worker Ember servers. Returns active task count and uptime.",
        "input_schema": {
            "type": "object",
            "properties": {
                "brother": {
                    "type": "string",
                    "description": "Specific worker to check. If not provided, checks all workers.",
                },
            },
        },
    },
    {
        "name": "list_worker_tasks",
        "description": "List active tasks (aspens) on worker Ember servers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "brother": {
                    "type": "string",
                    "description": "Specific worker to check. If not provided, checks all workers.",
                },
            },
        },
    },
    # --- Messaging ---
    {
        "name": "send_message",
        "description": "Send a message to one or more brothers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recipients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of brother names (e.g. ['oppy', 'jerry']).",
                },
                "body": {"type": "string", "description": "The message body."},
                "subject": {"type": "string", "description": "Optional subject line."},
                "task_id": {"type": "integer", "description": "Optional task ID to link this message to."},
            },
            "required": ["recipients", "body"],
        },
    },
    {
        "name": "check_mailbox",
        "description": "Check the mailbox for messages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "unread_only": {"type": "boolean", "description": "If true, only show unread messages."},
                "limit": {"type": "integer", "description": "Maximum number of messages to return."},
            },
        },
    },
    {
        "name": "read_message",
        "description": "Read a specific message by ID (also marks it as read).",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "integer", "description": "The message ID to read."},
            },
            "required": ["message_id"],
        },
    },
    {
        "name": "browse_feed",
        "description": "Browse the shared message feed. Shows all brother-to-brother messages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of messages to return."},
                "offset": {"type": "integer", "description": "Number of messages to skip (for pagination)."},
                "sender": {"type": "string", "description": "Filter by sender name."},
                "recipient": {"type": "string", "description": "Filter by recipient name."},
                "query": {"type": "string", "description": "Search keyword in subject and body."},
            },
        },
    },
    {
        "name": "unread_count",
        "description": "Get the number of unread messages in the mailbox.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    # --- Tasks ---
    {
        "name": "list_tasks",
        "description": "List tasks from the Hearth task tracker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "assignee": {"type": "string", "description": "Filter by assignee (e.g. 'oppy')."},
                "status": {
                    "type": "string",
                    "description": "Filter by status (pending, launched, in_progress, completed, failed).",
                },
                "limit": {"type": "integer", "description": "Maximum number of tasks to return."},
            },
        },
    },
    {
        "name": "get_task",
        "description": "Get full details of a specific task by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The task ID to fetch."},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "update_task",
        "description": "Update a task's status and/or output summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The task ID to update."},
                "status": {"type": "string", "description": "New status (e.g. 'in_progress', 'completed', 'failed')."},
                "output": {"type": "string", "description": "Output summary of what was done."},
                "parent_task_id": {"type": "integer", "description": "Parent task ID to reparent under."},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "retry_task",
        "description": "Retry a failed task. Creates a child task with the same prompt and sends it to the Ember.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The task ID to retry (must be 'failed')."},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "kill_task",
        "description": "Kill a running task. Terminates the tmux session on the Ember.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The task ID to kill."},
            },
            "required": ["task_id"],
        },
    },
    # --- Morsels ---
    {
        "name": "deposit_morsel",
        "description": "Deposit a morsel — a short note, observation, or log entry.",
        "input_schema": {
            "type": "object",
            "properties": {
                "body": {"type": "string", "description": "The morsel content."},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags (e.g. ['conductor-tick', 'debug']).",
                },
                "task_id": {"type": "integer", "description": "Optional task ID to link to."},
                "brother": {"type": "string", "description": "Optional brother name to link to."},
                "card_id": {"type": "integer", "description": "Optional kanban card ID to link to."},
            },
            "required": ["body"],
        },
    },
    {
        "name": "list_morsels",
        "description": "List morsels, optionally filtered by creator, tag, or linked object.",
        "input_schema": {
            "type": "object",
            "properties": {
                "creator": {"type": "string", "description": "Filter by creator name."},
                "tag": {"type": "string", "description": "Filter by tag."},
                "task_id": {"type": "integer", "description": "Filter by linked task ID."},
                "card_id": {"type": "integer", "description": "Filter by linked kanban card ID."},
                "limit": {"type": "integer", "description": "Maximum number of morsels to return."},
            },
        },
    },
    {
        "name": "get_morsel",
        "description": "Get full details of a specific morsel by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "morsel_id": {"type": "integer", "description": "The morsel ID to fetch."},
            },
            "required": ["morsel_id"],
        },
    },
    # --- Kanban Board ---
    {
        "name": "list_board",
        "description": "Show kanban board cards, grouped by column.",
        "input_schema": {
            "type": "object",
            "properties": {
                "col": {"type": "string", "description": "Filter to a specific column."},
                "assignee": {"type": "string", "description": "Filter by assignee."},
                "label": {"type": "string", "description": "Filter by label."},
                "include_archived": {"type": "boolean", "description": "Include archived cards."},
                "project": {"type": "string", "description": "Filter by project (e.g. 'clade', 'omtra')."},
            },
        },
    },
    {
        "name": "get_card",
        "description": "Get full details of a kanban card.",
        "input_schema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer", "description": "The card ID."},
            },
            "required": ["card_id"],
        },
    },
    {
        "name": "create_card",
        "description": "Create a kanban card.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Card title."},
                "description": {"type": "string", "description": "Card description."},
                "col": {"type": "string", "description": "Column: backlog, todo, in_progress, done, archived."},
                "priority": {"type": "string", "description": "Priority: low, normal, high, urgent."},
                "assignee": {"type": "string", "description": "Who is responsible."},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels/tags for categorization.",
                },
                "links": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Links to other objects. Each dict has object_type and object_id keys.",
                },
                "project": {"type": "string", "description": "Project name (e.g. 'clade', 'omtra')."},
            },
            "required": ["title"],
        },
    },
    {
        "name": "move_card",
        "description": "Move a kanban card to a different column.",
        "input_schema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer", "description": "The card ID to move."},
                "col": {"type": "string", "description": "Target column: backlog, todo, in_progress, done, archived."},
            },
            "required": ["card_id", "col"],
        },
    },
    {
        "name": "update_card",
        "description": "Update a kanban card's fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer", "description": "The card ID to update."},
                "title": {"type": "string", "description": "New title."},
                "description": {"type": "string", "description": "New description."},
                "priority": {"type": "string", "description": "New priority: low, normal, high, urgent."},
                "assignee": {"type": ["string", "null"], "description": "New assignee (null to unassign)."},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New labels (replaces existing).",
                },
                "project": {"type": ["string", "null"], "description": "Project name (null to clear)."},
            },
            "required": ["card_id"],
        },
    },
    {
        "name": "archive_card",
        "description": "Archive a kanban card (move to archived column).",
        "input_schema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer", "description": "The card ID to archive."},
            },
            "required": ["card_id"],
        },
    },
    # --- Trees ---
    {
        "name": "list_trees",
        "description": "List task trees (hierarchies of parent-child tasks).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of trees to return."},
            },
        },
    },
    {
        "name": "get_tree",
        "description": "Get a task tree showing the full hierarchy from a root task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "root_task_id": {"type": "integer", "description": "The root task ID."},
            },
            "required": ["root_task_id"],
        },
    },
    # --- Search ---
    {
        "name": "search",
        "description": (
            "Search across tasks, morsels, and cards using full-text search. "
            "Supports keyword search, prefix matching (e.g. 'deploy*'), and phrase queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "types": {"type": "string", "description": "Comma-separated entity types (e.g. 'task,card')."},
                "limit": {"type": "integer", "description": "Maximum number of results."},
                "created_after": {"type": "string", "description": "Filter results after this date (YYYY-MM-DD)."},
                "created_before": {"type": "string", "description": "Filter results before this date (YYYY-MM-DD)."},
            },
            "required": ["query"],
        },
    },
]
