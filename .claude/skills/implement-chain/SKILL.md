---
name: implement-chain
description: This skill should be used when the user asks to "implement a chain of cards", "implement cards in sequence", "chain card implementations", "implement-chain", or wants to delegate multiple kanban cards as a sequential implementation chain with parallel reviews using stacked branches. Trigger on any request involving ordered multi-card implementation delegation.
disable-model-invocation: true
---

# /implement-chain

Delegate a sequence of kanban cards as a chained implementation pipeline with parallel code reviews, using stacked git branches.

## Usage

```
/implement-chain <card_ids> [brother] [project]
```

- `card_ids` — comma-separated card IDs (e.g. `42,43,44`). Order matters: card 1 is implemented first.
- `brother` — optional worker name (default: `oppy`).
- `project` — optional project name (e.g. `omtra`, `clade`). Passed through to `initiate_ember_task`.

**Example:** `/implement-chain 42,43,44 oppy omtra`

## Execution Model (Option C — Parallel Reviews)

```
card1_impl → card2_impl → card3_impl
    └→ card1_review   └→ card2_review   └→ card3_review
```

- Implementation tasks form a linear chain: each blocked by the previous impl via `blocked_by_task_id`.
- Each review task is blocked only by its own card's impl task, so reviews run in parallel with subsequent implementations.
- For N cards: 2N tasks total. The impl chain is sequential; reviews overlap with later impls.

## Branching (Stacked Branches)

```
main ──→ card-42-auth ──→ card-43-session ──→ card-44-roles
              PR #1              PR #2              PR #3
         (targets main)   (targets card-42-auth)  (targets card-43-session)
```

Each card gets its own branch forked from the previous card's branch. PRs must merge in order.

## Procedure

### Step 1: Parse Arguments

Parse the args string. Expected format: `<card_ids> [brother] [project]`

- Split args on whitespace. First token is card IDs (comma-separated integers), second is optional brother name, third is optional project name.
- Default brother to `oppy` if not specified.
- Validate that at least one card ID is provided.

### Step 2: Fetch and Validate Cards

For each card ID, call `get_card(card_id)`. Validate:

- The card exists (if not, abort with error listing the missing card IDs).
- The card is NOT in `done` or `archived` column (if so, abort with error — these cards are already completed).

Collect each card's title for branch name generation.

### Step 3: Generate Branch Names

For each card, generate a branch name using the convention `card-<id>-<slug>`:

- Take the card title, lowercase it, replace spaces and non-alphanumeric characters with hyphens, collapse multiple hyphens, trim to 40 characters max, and strip leading/trailing hyphens.
- Example: card #42 "User Authentication" → `card-42-user-authentication`

Pre-determine ALL branch names before creating any tasks. Store them in an ordered list alongside their card IDs and titles.

### Step 4: Move Cards to in_progress

For each card, call `move_card(card_id, "in_progress")`.

### Step 5: Create Implementation Tasks

Create implementation tasks sequentially, chaining them via `blocked_by_task_id`.

For card at index `i` (0-based):

- **Parent branch:** `main` if `i == 0`, otherwise the branch name of card `i-1`.
- **New branch:** the branch name of card `i`.
- **blocked_by_task_id:** `None` if `i == 0`, otherwise the task ID of the impl task for card `i-1`.
- **target_branch:** set to the parent branch (so the worktree is created from it).
- **card_id:** the card's ID.
- **parent_task_id:** not set (these are top-level tasks in the chain).
- **project:** pass through the project arg if provided.

Call `initiate_ember_task` with these parameters. Use this prompt template for each implementation task:

```
## Implement Card #{card_id}: {card_title}

### Card Description
{card_description}

### Git Instructions
- Your worktree is based on branch `{parent_branch}`.
- Create and work on a new branch called `{new_branch}`.
- When done, push `{new_branch}` and create a PR targeting `{parent_branch}`.

### Chain Context
This card is #{position} of {total} in an implementation chain: {chain_summary}.
Branch stack: {branch_stack}

### Task Protocol
1. Update your task status to 'in_progress'.
2. Check card #{card_id} with `get_card` for full context.
3. Create branch `{new_branch}` from the current HEAD (which is `{parent_branch}`).
4. Implement the card's requirements.
5. Commit, push, and create a PR targeting `{parent_branch}`.
6. Update your task status to 'completed' with a summary of what was done.
```

Set `subject` to `Implement card #{card_id}: {card_title}`.

Store the returned task ID for each impl task — these are needed for both the chain ordering and the review task dependencies.

### Step 6: Create Review Tasks

For each card at index `i`, create a review task:

- **blocked_by_task_id:** the impl task ID for card `i` (NOT the previous impl — each review waits only for its own impl).
- **card_id:** the card's ID.
- **project:** pass through the project arg if provided.

For the **last** review task only, set `on_complete` to notify the conductor that the full chain is done:

```
on_complete: "The full implementation chain for cards {card_id_list} is complete. All implementations and reviews are finished. Branch stack: {branch_stack}. PRs should be merged in order: {merge_order}."
```

Use this prompt template for each review task:

```
## Review Card #{card_id}: {card_title}

### Review Target
- Branch to review: `{card_branch}`
- PR target branch: `{parent_branch}`

### Card Description
{card_description}

### Chain Context
This card is #{position} of {total} in an implementation chain: {chain_summary}.

### Review Instructions
1. Update your task status to 'in_progress'.
2. Check out or read the branch `{card_branch}`.
3. Review the implementation against the card requirements.
4. Check for:
   - Correctness: Does the implementation match the card description?
   - Code quality: Clean, readable, well-structured code?
   - Tests: Are there appropriate tests?
   - No regressions: Does this break anything from the parent branch?
5. If issues are found, push fix commits to `{card_branch}` or leave PR comments.
6. Move card #{card_id} to 'done' when the review passes.
7. Update your task status to 'completed' with a review summary.
```

Set `subject` to `Review card #{card_id}: {card_title}`.

### Step 7: Report the Chain

After all tasks are created, output a summary table:

```
## Implementation Chain Created

### Cards: {card_id_list}
### Worker: {brother}

| Card | Branch | Impl Task | Blocked By | Review Task | Blocked By |
|------|--------|-----------|------------|-------------|------------|
| #{id1}: {title1} | card-{id1}-{slug1} | #{impl1} | — | #{rev1} | #{impl1} |
| #{id2}: {title2} | card-{id2}-{slug2} | #{impl2} | #{impl1} | #{rev2} | #{impl2} |
| #{id3}: {title3} | card-{id3}-{slug3} | #{impl3} | #{impl2} | #{rev3} | #{impl3} |

### Branch Stack
main → card-{id1}-{slug1} → card-{id2}-{slug2} → card-{id3}-{slug3}

### Merge Order
PRs must merge in order: #{id1} → #{id2} → #{id3}

### Execution Timeline
1. card1 impl starts immediately
2. card1 review starts when card1 impl completes (card2 impl also starts)
3. card2 review starts when card2 impl completes (card3 impl also starts)
4. card3 review starts when card3 impl completes
5. on_complete fires when card3 review completes
```

## Error Handling

- **Missing card:** If any card ID doesn't exist, abort before creating any tasks. List all invalid IDs.
- **Card already done/archived:** If any card is in `done` or `archived`, abort with a message explaining which cards are already completed. Do not create partial chains.
- **Empty card list:** If no card IDs are provided, show usage instructions.
- **Single card:** A chain of 1 card is valid — it behaves like a single `/implement-card` invocation (one impl task + one review task, no blocking chain).

## Key API Parameters

All tasks use `initiate_ember_task` with these parameters:

| Parameter | Impl Tasks | Review Tasks |
|-----------|-----------|--------------|
| `brother` | from args | from args |
| `prompt` | impl prompt template | review prompt template |
| `subject` | `Implement card #N: title` | `Review card #N: title` |
| `card_id` | card's ID | card's ID |
| `blocked_by_task_id` | prev impl task ID (or None) | this card's impl task ID |
| `target_branch` | parent branch name | card's branch name |
| `on_complete` | not set | set on last review only |
| `project` | from args (if provided) | from args (if provided) |
