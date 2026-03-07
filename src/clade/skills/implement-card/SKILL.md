---
name: implement-card
description: Delegate a kanban card implementation to a worker brother with automatic review task chaining.
argument-hint: <card_id> [brother] [working_dir] [--plan]
disable-model-invocation: true
---

# Implement Card

Delegate a kanban card to a worker brother for implementation, then chain a blocked review task.

**Arguments:**
- `$1` — card ID (required)
- `$2` — brother name (default: `oppy`)
- `$3` — working directory override (optional)
- `$4` — `--plan` flag (optional): if provided, create a plan task before implementation

## Steps

### 1. Read the card and gather context

Call `get_card($1)`. If the card is not found, tell the user and stop.

Print a brief summary of the card (title, description, current column, labels).

**Gather the 1-hop neighborhood:** Check the card's links. For each linked item, pull it down:
- Linked cards → `get_card(id)` for each
- Linked morsels → `get_morsel(id)` for each
- Linked tasks → `get_task(id)` for each

Fetch all linked items in parallel where possible. Save their content — you'll include it in the delegation prompt (step 4).

### 2. Determine working directory

- If `$3` is provided, use it as `working_dir`
- Else if the card has a `project` field:
  - `"clade"` → `~/.local/share/clade`
  - `"omtra"` → `~/projects/mol_diffusion/OMTRA`
  - Otherwise, leave `working_dir` unset (brother default)
- Else leave `working_dir` unset

### 3. Move card to in_progress

Call `move_card($1, "in_progress")`.

### 4. Delegate plan task (conditional — only if `$4` is `--plan`)

If `$4` is `--plan`:

Set `brother` to `$2` if provided, otherwise `"oppy"`.

Build the plan prompt (include card title, description, and gathered context):

```
You are creating an implementation plan for kanban card #<card_id>: "<card_title>"

## Card Description
<card_description>

## Context
<For each linked item gathered in step 1, include a section:>

### Linked Card #<id>: <title>
<description>

### Linked Morsel #<id>
<body>

### Linked Task #<id>: <subject>
Status: <status>
<output or prompt summary>

<If no linked items, omit this section entirely.>

## Instructions

1. Read the project's CLAUDE.md to understand the codebase
2. Explore the relevant code — read key files, trace data flow, understand existing patterns
3. Write a detailed implementation plan: what to change, where, and why. Include specific file paths, function names, and any trade-offs or risks.
4. Deposit the plan as a morsel for the audit trail: `deposit_morsel(body=<plan>, tags=["plan", "card-<card_id>"])`
5. **Write the full plan into your task output and mark yourself complete — this is the primary handoff to the implementation task:**
   `update_task(task_id=<your task ID from CLAUDE_TASK_ID env var>, output=<full plan text>, status="completed")`
   The implementation task will automatically receive your plan via the predecessor context machinery.
```

Call `initiate_ember_task(brother=brother, prompt=<above>, subject="Plan card #<card_id>: <card_title>", card_id=$1, working_dir=<from step 2>)`.

Note the task ID as `plan_task_id`.

If `$4` is not `--plan`, skip this step entirely. Set `plan_task_id` to null/unset.

### 5. Delegate implementation task

Set `brother` to `$2` if provided, otherwise `"oppy"`.

Build the implementation prompt (use the card title and description verbatim, plus gathered context):

```
You are implementing kanban card #<card_id>: "<card_title>"

## Card Description
<card_description>

## Context
<For each linked item gathered in step 1, include a section:>

### Linked Card #<id>: <title>
<description>

### Linked Morsel #<id>
<body>

### Linked Task #<id>: <subject>
Status: <status>
<output or prompt summary>

<If no linked items, omit this section entirely.>

## Instructions

1. Read the project's CLAUDE.md to understand the codebase
2. If a plan was prepared (check your task's ancestor context — it will appear as "Predecessor (blocking task)" context), follow it. Also check for planning morsels tagged "plan" and "card-<card_id>" as a secondary source.
3. Create a feature branch: `card-<card_id>-<slug>` (slug = lowercase card title, spaces to hyphens, max 40 chars)
4. Implement the feature/fix described above
5. Run the project's test suite and fix any failures
6. Commit your changes with a clear commit message referencing card #<card_id>
7. Push the branch: `git push -u origin <branch_name>`
8. Open a PR: `gh pr create --title "<card_title>" --body "Implements card #<card_id>\n\n<card_description>"`
9. Send a message to doot summarizing what you did and the PR URL
```

If `plan_task_id` is set (i.e., `--plan` was used):
Call `initiate_ember_task(brother=brother, prompt=<above>, subject="Implement card #<card_id>: <card_title>", card_id=$1, working_dir=<from step 2>, blocked_by_task_id=plan_task_id)`.

Otherwise:
Call `initiate_ember_task(brother=brother, prompt=<above>, subject="Implement card #<card_id>: <card_title>", card_id=$1, working_dir=<from step 2>)`.

Note the implementation task ID from the response.

### 6. Delegate review task (blocked by implementation)

Build the senior review prompt (include the same context from step 1):

```
You are reviewing the implementation of kanban card #<card_id>: "<card_title>"

## Card Description
<card_description>

## Context
<Same linked item sections as the implementation prompt — cards, morsels, tasks from step 1.>
<If no linked items, omit this section entirely.>

## Instructions

1. Read the project's CLAUDE.md to understand the codebase
2. Fetch latest: `git fetch origin`
3. Find the branch for this card (starts with `card-<card_id>-`)
4. Check out the branch
5. Review the diff against main: `git diff origin/main...HEAD`
6. Check:
   - Does the implementation match the card description?
   - Are there any bugs or edge cases?
   - Do all tests pass?
   - Is the code style consistent with the rest of the codebase?
7. If you find issues, fix them directly — commit and push
8. Post a review comment on the PR using `gh pr review --comment -b "<your review>"` summarizing your findings — what looked good, what you fixed, any concerns. Do this even if everything looks good.
```

Call `initiate_ember_task(brother=brother, prompt=<above>, subject="Review card #<card_id>: <card_title>", card_id=$1, working_dir=<from step 2>, blocked_by_task_id=<implementation task ID from step 5>)`.

### 7. Report

Tell the user:
- If `--plan` was used: plan task ID and that it's been delegated to `<brother>`
- Implementation task ID (and that it's blocked until plan completes, if `--plan` was used)
- Review task ID and that it's blocked until implementation completes
- The card has been moved to in_progress

$ARGUMENTS
