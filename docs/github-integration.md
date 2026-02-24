# GitHub Integration

Connect your GitHub repositories to the Hearth so that pull requests are automatically enriched with kanban card context and linked back to the board.

## What It Does

When you open a PR from a branch named `card-<N>-*` (e.g. `card-42-add-login`), the **Hearth-PR Bridge** workflow:

1. Extracts the card ID from the branch name
2. Fetches card details, linked tasks, and tree status from the Hearth
3. Appends a **Hearth Context** section to the PR body with card metadata, linked tasks, and tree progress
4. Links the PR back to the card on the kanban board
5. Deposits a morsel recording the PR event

PRs from branches that don't match the `card-*` pattern are ignored.

## Prerequisites

- A running Hearth server (see [QUICKSTART.md](QUICKSTART.md))
- The `gh` CLI installed and authenticated on your local machine ([install](https://cli.github.com/))
- Admin or push access to the target GitHub repo (needed to set secrets)

## Setup

### Step 1: Install the bridge on a repo

From the root of any git repo with a GitHub remote:

```bash
clade setup-github
```

This single command:
- Detects `owner/repo` from your git remote
- Generates a dedicated API key (`github-actions-<owner>-<repo>`) and registers it with the Hearth
- Sets `HEARTH_URL` and `HEARTH_API_KEY` as GitHub repo secrets
- Writes the workflow file to `.github/workflows/hearth-bridge.yml`

If your Hearth uses a self-signed certificate:

```bash
clade setup-github --no-verify-ssl
```

### Step 2: Commit and push the workflow

```bash
git add .github/workflows/hearth-bridge.yml
git commit -m "ci: add Hearth-PR bridge workflow"
git push
```

The workflow activates immediately for new PRs.

### Step 3: Test it

1. Create a card on the kanban board (note its ID, e.g. `42`)
2. Create a branch: `git checkout -b card-42-test-bridge`
3. Make a change, commit, push, and open a PR
4. The PR body should be updated within ~30 seconds with the Hearth Context section

## Setting Up `gh` on Remote Brothers

If your brothers need GitHub access (e.g. to create PRs from remote machines), authenticate the `gh` CLI on their hosts:

```bash
clade setup-gh-auth <brother-name>
```

This will:
1. Check if `gh` is installed on the remote (install it if missing via apt/dnf/brew/pacman)
2. Prompt you for a GitHub Personal Access Token
3. Authenticate `gh` on the remote machine

Create a PAT at [github.com/settings/tokens](https://github.com/settings/tokens). The token needs `repo` scope at minimum.

Example:

```bash
$ clade setup-gh-auth oppy
Checking gh CLI on ian@masuda...
  gh CLI installed
A GitHub Personal Access Token (PAT) is needed to authenticate.
Create one at: https://github.com/settings/tokens
GitHub PAT: ****
Authenticating gh on ian@masuda...
gh CLI authenticated successfully!
  Logged in to github.com as Dunni3
```

## How the Workflow Works

The workflow (`.github/workflows/hearth-bridge.yml`) runs on `pull_request: [opened]` events. It uses two repo secrets:

| Secret | Purpose |
|--------|---------|
| `HEARTH_URL` | Base URL of your Hearth server |
| `HEARTH_API_KEY` | API key for authenticating with the Hearth |

The workflow is fully repo-agnostic -- it uses `${{ github.repository }}` to construct PR links, so the same workflow file works on any repo without modification.

### PR Body Output

For a PR opened from `card-42-add-login`, the appended section looks like:

```
---

## Hearth Context

| Field | Value |
|-------|-------|
| Card | #42: Add user login |
| Column | in_progress |
| Priority | high |
| Assignee | oppy |
| Labels | auth, frontend |
| Project | myapp |

### Linked Tasks

| Task | Subject | Status | Assignee |
|------|---------|--------|----------|
| #101 | Implement login API | completed | oppy |
| #102 | Add login form | in_progress | jerry |

### Linked Trees

- **Tree #101**: Implement login API (2 completed, 1 in progress, 0 failed, 0 pending)
```

## Multi-Repo Setup

Run `clade setup-github` from each repo you want to connect. Each repo gets its own API key and secrets. All repos share the same Hearth server.

```bash
cd ~/projects/my-app && clade setup-github
cd ~/projects/my-lib && clade setup-github
```

## Troubleshooting

**"gh CLI not found"** -- Install from https://cli.github.com/ and ensure it's on your PATH.

**"gh CLI not authenticated"** -- Run `gh auth login` and follow the prompts.

**"Could not detect a GitHub repo"** -- Make sure you're in a git repo with an `origin` remote pointing to GitHub (SSH or HTTPS format).

**Secrets not being set** -- You need admin or collaborator access to the repo. Check with `gh secret list --repo owner/repo`.

**Workflow runs but PR body not updated** -- Check the Actions tab on GitHub for the workflow run. Common issues:
- Hearth server unreachable from GitHub Actions (must be publicly accessible or via a tunnel)
- Self-signed cert: the workflow uses `curl -sk` which skips cert verification, so this should work
- Card not found: verify the card ID exists on the board

**"Warning: could not reach Hearth"** -- Non-fatal. The API key was saved locally but couldn't be registered with the Hearth. You can register it manually later or re-run the command when the Hearth is reachable.
