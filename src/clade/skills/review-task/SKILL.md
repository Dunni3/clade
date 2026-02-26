---
name: review-task
description: Delegate a senior code review for a completed task, automatically inferring the correct PR branch.
argument-hint: <task_id> [brother]
disable-model-invocation: true
---

# Review Task

Delegate a senior code review for a completed task to a worker brother, automatically inferring the correct branch via linked cards and PR search.

**Arguments:**
- `$1` — task ID to review (required)
- `$2` — brother name (default: `oppy`)

## Steps

### 1. Fetch the task

Call `get_task($1)`. If the task is not found, tell the user and stop.

Print a brief summary of the task (subject, status, assignee, output).

### 2. Extract card IDs

Look for linked card IDs in the task details. Tasks created via `implement-card` are typically linked to a kanban card.

If no card is linked, tell the user and proceed to the fallback in step 3.

### 3. Infer the branch

Try each strategy in order until one succeeds:

**Strategy A — PR search via linked card:**
For each linked card ID, run:
```
gh pr list --repo dunni3/clade --search "card #<card_id>" --json number,headRefName --limit 1
```
If a PR is found, use its `headRefName` as `target_branch`.

**Strategy B — Parse task output for PR URL:**
Search the task output for a GitHub PR URL matching `github.com/.*/pull/(\d+)`. If found, run:
```
gh pr view <number> --repo dunni3/clade --json headRefName
```
Use the result as `target_branch`.

**Strategy C — Branch naming convention:**
Try to find a branch matching the card-based convention:
```
git ls-remote --heads origin "card-<card_id>-*"
```
If exactly one branch matches, use it as `target_branch`.

If all strategies fail, tell the user that no branch could be inferred and ask them to provide one manually. Stop.

Print the inferred branch name.

### 4. Determine the card and working directory

If a card was found in step 2, call `get_card(<card_id>)` and:
- Use the card's `project` field to determine `working_dir`:
  - `"clade"` → `~/.local/share/clade`
  - `"omtra"` → `~/projects/mol_diffusion/OMTRA`
  - Otherwise, leave `working_dir` unset
- Note the `card_id` for linking

If no card was found, leave `working_dir` and `card_id` unset.

### 5. Delegate review task

Set `brother` to `$2` if provided, otherwise `"oppy"`.

Build the senior review prompt:

```
You are reviewing the implementation of task #<task_id>: "<task_subject>"

## Task Details
<task output summary, if available>

## Instructions

1. Read the project's CLAUDE.md to understand the codebase
2. Check out the branch and review the diff against main: `git diff main...HEAD`
3. Check:
   - Does the implementation match the task description?
   - Are there any bugs or edge cases?
   - Do all tests pass?
   - Is the code style consistent with the rest of the codebase?
4. If you find issues, fix them directly — commit and push
5. Post a review comment on the PR using `gh pr review --comment -b "<your review>"` summarizing your findings — what looked good, what you fixed, any concerns. Do this even if everything looks good.
```

Call `initiate_ember_task(brother=brother, prompt=<above>, subject="Review task #<task_id>: <task_subject>", parent_task_id=$1, card_id=<card_id if found>, working_dir=<from step 4>, target_branch=<from step 3>)`.

### 6. Report

Tell the user:
- The inferred branch name and how it was found (card PR search, task output, or naming convention)
- Review task ID and that it's been delegated to `<brother>`
- The card it's linked to (if any)

$ARGUMENTS
