# MCP Tool Reference

Tool signatures for each MCP server type. For implementation details, see [architecture.md](architecture.md).

## Coordinator tools (clade-personal)

- `list_brothers()` — List available brother instances
- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `initiate_ember_task(brother, prompt, subject?, parent_task_id?, working_dir?, max_turns?, card_id?, on_complete?, blocked_by_task_id?)` — **Primary delegation path.** Delegate a task to a brother via their Ember server. Supports deferred execution via `blocked_by_task_id`.
- `initiate_ssh_task(brother, prompt, subject?, working_dir?, max_turns?, auto_pull?, parent_task_id?, on_complete?, card_id?)` — Delegate a task via SSH + tmux (legacy path)
- `list_tasks(assignee?, status?, limit?)`, `get_task(task_id)`, `update_task(task_id, ...)` — Task management
- `kill_task(task_id)` — Kill a running task (terminates tmux session on Ember, marks as `killed`)
- `retry_task(task_id)` — Retry a failed task (creates child task with same prompt, sends to Ember)
- `deposit_morsel(body, tags?, task_id?, brother?, card_id?)` — Deposit an observation/note
- `list_morsels(creator?, tag?, task_id?, card_id?, limit?)` — List morsels with filters
- `list_trees(limit?)` — List task trees with status summaries
- `get_tree(root_task_id)` — Get full task tree hierarchy
- `check_ember_health(brother?, url?)` — Check Ember health (by brother name, URL, or all brothers in registry)
- `list_ember_tasks(brother?)` — List active tasks on Ember(s) (by brother name or all)
- `create_card`, `list_board`, `get_card`, `move_card`, `update_card`, `archive_card` — Kanban board

## Conductor tools (clade-conductor)

- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `list_tasks`, `get_task`, `update_task` — Task visibility and status updates
- `delegate_task(brother, prompt, subject?, parent_task_id?, working_dir?, max_turns?, card_id?, on_complete?, blocked_by_task_id?)` — Delegate a task to a worker via Ember. Auto-reads `TRIGGER_TASK_ID` from env for parent linking when `parent_task_id` is not explicitly set. Supports deferred execution via `blocked_by_task_id`.
- `check_worker_health(worker?)` — Check one or all worker Ember servers
- `list_worker_tasks(worker?)` — List active tasks on worker Embers
- `deposit_morsel(body, tags?, task_id?, brother?, card_id?)` — Deposit an observation/note
- `list_morsels(creator?, tag?, task_id?, card_id?, limit?)` — List morsels with filters
- `list_trees(limit?)` — List task trees with status summaries
- `get_tree(root_task_id)` — Get full task tree hierarchy
- `create_card`, `list_board`, `get_card`, `move_card`, `update_card`, `archive_card` — Kanban board

## Worker tools (clade-worker)

- `send_message`, `check_mailbox`, `read_message`, `browse_feed`, `unread_count` — Mailbox communication
- `list_tasks`, `get_task`, `update_task`, `kill_task`, `retry_task` — Task visibility, status updates, kill, and retry
- `initiate_ember_task(brother, prompt, subject?, parent_task_id?, working_dir?, max_turns?, card_id?, on_complete?, blocked_by_task_id?)` — Delegate tasks to sibling brothers via their Embers
- `deposit_morsel(body, tags?, task_id?, brother?, card_id?)` — Deposit an observation/note
- `list_morsels(creator?, tag?, task_id?, card_id?, limit?)` — List morsels with filters
- `list_trees(limit?)` — List task trees with status summaries
- `get_tree(root_task_id)` — Get full task tree hierarchy
- `check_ember_health(brother?, url?)` — Check Ember health (local or by brother name)
- `list_ember_tasks(brother?)` — List active tasks on Ember(s)
- `create_card`, `list_board`, `get_card`, `move_card`, `update_card`, `archive_card` — Kanban board
