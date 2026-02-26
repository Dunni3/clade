---
name: implement-card
description: Delegate a kanban card implementation to a worker brother with automatic review task chaining.
argument-hint: <card_id> [brother] [working_dir]
disable-model-invocation: true
---

# Implement Card

Delegate a kanban card to a worker brother for implementation, then chain a blocked review task.

**Arguments:**
- `$1` — card ID (required)
- `$2` — brother name (default: `oppy`)
- `$3` — working directory override (optional)

## Steps

### 1. Read the card

Call `get_card($1)`. If the card is not found, tell the user and stop.

Print a brief summary of the card (title, description, current column, labels).

### 2. Determine working directory

- If `$3` is provided, use it as `working_dir`
- Else if the card has a `project` field:
  - `"clade"` → `~/.local/share/clade`
  - `"omtra"` → `~/projects/mol_diffusion/OMTRA`
  - Otherwise, leave `working_dir` unset (brother default)
- Else leave `working_dir` unset

### 3. Move card to in_progress

Call `move_card($1, "in_progress")`.

### 4. Delegate implementation task

Set `brother` to `$2` if provided, otherwise `"oppy"`.

Build the implementation prompt (use the card title and description verbatim):

```
You are implementing kanban card #<card_id>: "<card_title>"

## Card Description
<card_description>

## Instructions

1. Read the project's CLAUDE.md to understand the codebase
2. Create a feature branch: `card-<card_id>-<slug>` (slug = lowercase card title, spaces to hyphens, max 40 chars)
3. Implement the feature/fix described above
4. Run the project's test suite and fix any failures
5. Commit your changes with a clear commit message referencing card #<card_id>
6. Push the branch: `git push -u origin <branch_name>`
7. Open a PR: `gh pr create --title "<card_title>" --body "Implements card #<card_id>\n\n<card_description>"`
8. Send a message to doot summarizing what you did and the PR URL
```

Call `initiate_ember_task(brother=brother, prompt=<above>, subject="Implement card #<card_id>: <card_title>", card_id=$1, working_dir=<from step 2>)`.

Note the task ID from the response.

### 5. Delegate review task (blocked)

Build the senior review prompt:

```
You are reviewing the implementation of kanban card #<card_id>: "<card_title>"

## Card Description
<card_description>

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

Call `initiate_ember_task(brother=brother, prompt=<above>, subject="Review card #<card_id>: <card_title>", card_id=$1, working_dir=<from step 2>, blocked_by_task_id=<task ID from step 4>)`.

### 6. Report

Tell the user:
- Implementation task ID and that it's been delegated to `<brother>`
- Review task ID and that it's blocked until implementation completes
- The card has been moved to in_progress

$ARGUMENTS
