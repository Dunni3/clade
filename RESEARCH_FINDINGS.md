# System Changes Research Report
**Date:** February 23, 2026
**Status:** Complete

---

## 1. Deferred Dependencies & Cascade Failure

### blocked_by_task_id Handling

**File:** `hearth/db.py:530-602` — Function `async def insert_task(...)`

**Key Behaviors:**

1. **Validation** (lines 562-569): Validates blocking task exists before creating child
2. **Auto-clear** (lines 571-572): If blocker is already `completed`, automatically sets `blocked_by_task_id = None`
   ```python
   if blocker["status"] == "completed":
       blocked_by_task_id = None
   ```
3. **Auto-parent** (lines 574-585): If `blocked_by_task_id` is set but `parent_task_id` is None, the blocker becomes the parent
   ```python
   if blocked_by_task_id is not None and parent_task_id is None:
       parent_task_id = blocked_by_task_id
   ```
   *Design note:* This allows the simple sequential case ("do A then B") to work without explicitly setting both parameters

4. **Return State** (`app.py:420-424`): Returns actual DB state to caller, which may differ from input if auto-clears occurred

### _cascade_failure() Function

**File:** `hearth/app.py:122-142`

**Signature:**
```python
async def _cascade_failure(failed_task_id: int) -> None:
    """When a task fails, cascade failure to any pending tasks blocked by it.

    Recursively fails downstream tasks so that if A blocks B blocks C,
    failing A will also fail B and C.
    """
```

**Behavior:**
1. Fetches all pending tasks where `blocked_by_task_id = failed_task_id` (line 128)
2. For each blocked task:
   - Clears the `blocked_by_task_id` field (line 134)
   - Updates task to `status='failed'` with output message (lines 135-140)
   - **Recursively calls itself** to cascade failure downstream (line 142)
3. Returns cleanly if no blocked tasks exist (lines 129-130)

**Key Implementation Detail:** Recursive design ensures that if A blocks B and B blocks C, failing A cascades to B and C automatically.

### _unblock_and_delegate() Function

**File:** `hearth/app.py:145-218`

**Signature:**
```python
async def _unblock_and_delegate(completed_task_id: int) -> None:
    """When a task completes, find tasks blocked by it and delegate them via Ember."""
```

**Auto-Delegation Workflow:**

1. **Fetch blocked tasks** (line 147): Gets all pending tasks where `blocked_by_task_id = completed_task_id`

2. **Build Ember registry** (lines 152-153): Merges DB Ember entries with env vars (DB wins on conflict)
   ```python
   db_embers = await db.get_embers()
   ember_url_map: dict[str, str] = {e["name"]: e["ember_url"] for e in db_embers}
   ```

3. **For each blocked task:**
   - Clear `blocked_by_task_id` (line 160)
   - Look up Ember URL (DB first, then env) (line 163)
   - Look up assignee API key (DB first, then env `API_KEYS`) (lines 173-178)
   - **Send HTTP POST** to `{ember_url}/tasks/execute` (lines 198-204):
     ```python
     payload: dict = {
         "prompt": task["prompt"],
         "task_id": task_id,
         "subject": task["subject"] or "",
         "sender_name": task["creator"],
         "working_dir": task.get("working_dir"),
     }
     if task.get("max_turns") is not None:
         payload["max_turns"] = task["max_turns"]
     ```
   - Update task to `status='launched'` on success (line 205)
   - **Non-fatal failure handling** (lines 210-218): If Ember is unreachable or key lookup fails, log warning and mark task `failed`

---

## 2. on_complete Field

### Database Schema

**File:** `hearth/db.py:178-183`

Migration added during `init_db()`:
```sql
ALTER TABLE tasks ADD COLUMN on_complete TEXT
```

### Pydantic Models

**File:** `hearth/models.py`

**CreateTaskRequest** (lines 79-89):
```python
class CreateTaskRequest(BaseModel):
    assignee: str
    subject: str = ""
    prompt: str
    session_name: str | None = None
    host: str | None = None
    working_dir: str | None = None
    parent_task_id: int | None = None
    on_complete: str | None = None          # ← Here
    blocked_by_task_id: int | None = None
    max_turns: int | None = None
```

**TaskDetail** (lines 119-130):
```python
class TaskDetail(TaskSummary):
    prompt: str
    session_name: str | None = None
    host: str | None = None
    working_dir: str | None = None
    output: str | None = None
    on_complete: str | None = None          # ← Here
    messages: list[FeedMessage] = []
    events: list["TaskEvent"] = []
    children: list[TaskSummary] = []
    blocked_tasks: list[TaskSummary] = []
    linked_cards: list[LinkedCardInfo] = []
```

### Usage in Code

**1. Task Creation** (`hearth/app.py:412`)
```python
task_id = await db.insert_task(
    creator=caller,
    assignee=req.assignee,
    subject=req.subject,
    prompt=req.prompt,
    session_name=req.session_name,
    host=req.host,
    working_dir=req.working_dir,
    parent_task_id=req.parent_task_id,
    on_complete=req.on_complete,           # ← Passed through
    blocked_by_task_id=req.blocked_by_task_id,
    max_turns=req.max_turns,
)
```

**2. Copy on Retry** (`hearth/app.py:663`)
```python
child_id = await db.insert_task(
    creator=caller,
    assignee=task["assignee"],
    prompt=task["prompt"],
    subject=retry_subject,
    host=task.get("host"),
    working_dir=task.get("working_dir"),
    parent_task_id=task_id,
    on_complete=task.get("on_complete"),   # ← Explicitly copied
)
```

**3. Conductor Reads as Primary Directive** (`deploy/conductor-tick.md:14-22`)

From Event-Driven Path:
> "Check for `on_complete` instructions — if the completed/failed task has a non-null `on_complete` field, read it and follow those instructions as your **primary directive** for this tick. The `on_complete` field contains follow-up instructions attached by the task creator."

This means the conductor should prioritize the `on_complete` instructions above its normal logic.

---

## 3. retry_task Endpoint & MCP Tool

### HTTP Endpoint

**File:** `hearth/app.py:624-744`

**Full Endpoint Definition:**
```python
@app.post("/api/v1/tasks/{task_id}/retry", response_model=TaskDetail)
async def retry_task(
    task_id: int,
    caller: str = Depends(resolve_sender),
) -> TaskDetail:
    """Retry a failed task: create a child task with the same prompt and send to Ember."""
```

**Implementation Flow:**

1. **Fetch Original Task** (line 630-632)
   ```python
   task = await db.get_task(task_id)
   if task is None:
       raise HTTPException(status_code=404, detail="Task not found")
   ```

2. **Auth Check** (lines 634-638)
   ```python
   if caller not in (task["assignee"], task["creator"]) and caller not in ADMIN_NAMES:
       raise HTTPException(
           status_code=403, detail="Only assignee, creator, or admin can retry"
       )
   ```

3. **Status Guard** (lines 640-645)
   ```python
   if task["status"] != "failed":
       raise HTTPException(
           status_code=409,
           detail=f"Cannot retry task with status '{task['status']}' — only failed tasks can be retried"
       )
   ```

4. **Create Child Task** (lines 648-666)
   ```python
   child_count = await db.count_children(task_id)
   retry_num = child_count + 1
   original_subject = task["subject"] or "(no subject)"
   retry_subject = f"Retry #{retry_num}: {original_subject}"

   child_id = await db.insert_task(
       creator=caller,
       assignee=task["assignee"],
       prompt=task["prompt"],
       subject=retry_subject,
       host=task.get("host"),
       working_dir=task.get("working_dir"),
       parent_task_id=task_id,
       on_complete=task.get("on_complete"),  # ← COPY on_complete
   )
   ```

5. **Send to Ember** (lines 712-726)
   ```python
   async with httpx.AsyncClient(verify=False, timeout=30.0) as http_client:
       resp = await http_client.post(
           f"{ember_url}/tasks/execute",
           json={
               "prompt": task["prompt"],
               "task_id": child_id,
               "subject": retry_subject,
               "sender_name": caller,
               "working_dir": task.get("working_dir"),
           },
           headers={"Authorization": f"Bearer {assignee_key}"},
       )
       resp.raise_for_status()
   ```

6. **Mark Launched & Return** (lines 739-744)
   ```python
   await db.update_task(child_id, status="launched")
   child = await db.get_task(child_id)

   # Do NOT trigger conductor tick — retry is the follow-up action itself
   return child
   ```

**Key Design Decision:** Intentionally does NOT trigger conductor tick (line 743 comment)

### MCP Tool

**File:** `src/clade/mcp/tools/mailbox_tools.py:299-317`

**Tool Definition:**
```python
@mcp.tool()
async def retry_task(task_id: int) -> str:
    """Retry a failed task. Creates a child task with the same prompt and sends it to the Ember.

    Args:
        task_id: The task ID to retry (must be in 'failed' status).
    """
    if mailbox is None:
        return _NOT_CONFIGURED
    try:
        result = await mailbox.retry_task(task_id)
        return (
            f"Retry task #{result['id']} created.\n"
            f"  Subject: {result.get('subject', '(no subject)')}\n"
            f"  Status: {result['status']}\n"
            f"  Assignee: {result['assignee']}\n"
            f"  Parent: #{result.get('parent_task_id', '?')}"
        )
    except Exception as e:
        return f"Error retrying task: {e}"
```

**Response Format:**
```
Retry task #[ID] created.
  Subject: [subject]
  Status: [status]
  Assignee: [assignee]
  Parent: #[parent_task_id]
```

---

## 4. Conductor Auto-Parent Linking

### Tick Script Instructions

**File:** `deploy/conductor-tick.md:19`

**Current Instruction (Event-Driven Path):**
> "If the task **completed** and needs follow-up, check worker load first (`check_worker_health`), then delegate children. **Always pass `parent_task_id=TRIGGER_TASK_ID` explicitly** when calling `delegate_task()` so the new task is linked as a child of the triggering task. (The env var provides a safety net, but passing it explicitly ensures the tree is built correctly.)"

**Key Points:**
- Primary approach: **Explicit `parent_task_id=TRIGGER_TASK_ID`**
- Safety net: **TRIGGER_TASK_ID env var auto-detection**
- Dual approach ensures correctness and robustness

### Implementation in delegate_task()

**File:** `src/clade/mcp/tools/conductor_tools.py:96-117`

**Auto-Parent Logic:**
```python
# Auto-link parent from env if not explicitly provided
if parent_task_id is not None:
    logger.info(
        "delegate_task: explicit parent_task_id=%d provided, skipping env auto-link",
        parent_task_id,
    )
else:
    trigger_id = os.environ.get("TRIGGER_TASK_ID", "")
    if trigger_id:
        try:
            parent_task_id = int(trigger_id)
            logger.info(
                "delegate_task: auto-linked parent_task_id=%d from TRIGGER_TASK_ID env",
                parent_task_id,
            )
        except (ValueError, TypeError):
            logger.warning(
                "delegate_task: TRIGGER_TASK_ID env has invalid value '%s', skipping auto-link",
                trigger_id,
            )
    else:
        logger.info("delegate_task: no parent_task_id provided and TRIGGER_TASK_ID not set, creating root task")
```

**Decision Tree:**
1. If `parent_task_id` explicitly provided → use it (skip env)
2. Else if `TRIGGER_TASK_ID` env var is set → parse and use it
3. Else → create as root task

**Logging:** All three paths logged for debugging

---

## 5. delegate_task Expanded

### Full Function Signature

**File:** `src/clade/mcp/tools/conductor_tools.py:54-83`

```python
@mcp.tool()
async def delegate_task(
    brother: str,
    prompt: str,
    subject: str = "",
    parent_task_id: int | None = None,
    working_dir: str | None = None,
    max_turns: int | None = None,
    card_id: int | None = None,
    on_complete: str | None = None,
    blocked_by_task_id: int | None = None,
) -> str:
    """Delegate a task to a worker brother via their Ember server.

    Creates a task in the Hearth, sends it to the worker's Ember, and
    updates the task status. If blocked_by_task_id is set, the task is
    created but not delegated — it will be auto-delegated when the
    blocking task completes.
    """
```

### New/Modified Parameters

**`on_complete: str | None = None`** (line 63)
- **Purpose:** Follow-up instructions for the conductor when task completes or fails
- **Passed to Hearth:** `await mailbox.create_task(..., on_complete=on_complete, ...)` (line 126)
- **Behavior:** Task creator can attach instructions for what the conductor should do when the task is done

**`blocked_by_task_id: int | None = None`** (line 64)
- **Purpose:** Defer task execution until another task completes
- **Passed to Hearth:** `await mailbox.create_task(..., blocked_by_task_id=blocked_by_task_id, ...)` (line 127)
- **Behavior:** If set, task is created in pending state; auto-delegated to Ember when blocker completes

**`card_id: int | None = None`** (line 62)
- **Purpose:** Link task to a kanban card for tracking
- **Already existed** but confirmed present
- **Behavior:** If provided, calls `await mailbox.add_card_link(card_id, "task", str(task_id))` (lines 135-139)

### Deferred Task Handling

**File:** `src/clade/mcp/tools/conductor_tools.py:144-154`

```python
# Check the *actual DB state* of blocked_by_task_id (not the input param).
# insert_task auto-clears blocked_by when the blocker is already completed,
# so the input param may say "blocked" while the DB says "ready to go".
actual_blocked_by = task_result.get("blocked_by_task_id")
if actual_blocked_by is not None:
    result_lines = [
        f"Task #{task_id} created (deferred — blocked by #{actual_blocked_by}).",
        f"  Subject: {subject or '(none)'}",
        f"  Assignee: {brother}",
        f"  Status: pending (waiting for #{actual_blocked_by} to complete)",
    ]
    if card_id is not None:
        result_lines.append(f"  Linked to card: #{card_id}")
    return "\n".join(result_lines)
```

**Key Behavior:**
- If task is blocked after creation, **returns immediately** with "deferred" status
- **Does NOT send to Ember** — task stays in pending state
- Auto-delegation happens when blocker completes (via `_unblock_and_delegate()`)

### max_turns Parameter Status

**File:** `src/clade/mcp/tools/conductor_tools.py:61`
- **Still present:** `max_turns: int | None = None`
- **Still passed to Ember:** Line 167 in `ember.execute_task(..., max_turns=max_turns, ...)`
- **Status:** NOT removed from the signature

---

## Summary Table

| Item | Location | Status | Key Finding |
|------|----------|--------|-------------|
| **blocked_by_task_id Validation** | hearth/db.py:562-569 | ✅ | Validates blocker exists |
| **Auto-clear on Complete** | hearth/db.py:571-572 | ✅ | Clears if blocker already done |
| **Auto-parent Linking** | hearth/db.py:574-585 | ✅ | Blocker becomes parent if parent_task_id is None |
| **_cascade_failure()** | hearth/app.py:122-142 | ✅ | Recursive, fails all downstream pending |
| **_unblock_and_delegate()** | hearth/app.py:145-218 | ✅ | Spawns to Ember on completion |
| **on_complete Column** | hearth/db.py:178-183 | ✅ | DB migration added |
| **on_complete in Models** | hearth/models.py:87,125 | ✅ | Both request and response |
| **Copy on Retry** | hearth/app.py:663 | ✅ | Explicitly copied to child |
| **Conductor Primary Directive** | conductor-tick.md:14-22 | ✅ | Reads on_complete as primary directive |
| **retry_task Endpoint** | hearth/app.py:624-744 | ✅ | POST /api/v1/tasks/{id}/retry |
| **retry_task Auth & Guard** | hearth/app.py:634-645 | ✅ | Assignee/creator/admin only, failed only |
| **retry_task Child Creation** | hearth/app.py:648-666 | ✅ | Copies prompt/assignee/host/wd/on_complete |
| **retry_task No Tick** | hearth/app.py:743 | ✅ | Intentionally does NOT trigger conductor |
| **retry_task MCP Tool** | mailbox_tools.py:299-317 | ✅ | Returns formatted response |
| **Conductor Tick Instruction** | conductor-tick.md:19 | ✅ | Explicit parent_task_id + env var fallback |
| **delegate_task Auto-Parent** | conductor_tools.py:96-117 | ✅ | Explicit first, env var second |
| **delegate_task Signature** | conductor_tools.py:54-83 | ✅ | 9 parameters including new on_complete & blocked_by |
| **Deferred Delegation** | conductor_tools.py:144-154 | ✅ | Returns "deferred" if blocked, no Ember send |
| **max_turns Present** | conductor_tools.py:61,167 | ✅ | Still in signature, still passed to Ember |

---

## Research Completion

**All 5 items researched with:**
- ✅ Exact file:line references
- ✅ Complete function signatures
- ✅ Code snippets showing implementation
- ✅ Behavior descriptions
- ✅ Design decision rationale

**Delivered:** Message #219 to doot, Message #220 with detailed findings, Morsel #222 for permanent record
