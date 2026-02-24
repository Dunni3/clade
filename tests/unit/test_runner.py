"""Tests for the local runner script generation."""

from clade.worker.runner import build_runner_script


class TestBuildRunnerScriptWorktree:
    """Test worktree logic in generated runner scripts."""

    def test_default_worktree_from_head(self):
        """Without target_branch, worktree fetches origin and creates from origin/main."""
        _, runner_path = build_runner_script(
            session_name="task-oppy-test-123",
            working_dir="/tmp/repo",
            prompt="do stuff",
        )
        with open(runner_path) as f:
            content = f.read()

        # Should fetch origin for fresh base
        assert "git fetch origin" in content
        # Should try origin/main first, then local branch, then HEAD detach
        assert 'git worktree add "$_WT_DIR" -b "clade/task-oppy-test-123" origin/main' in content
        assert 'git worktree add "$_WT_DIR" -b "clade/task-oppy-test-123"' in content
        assert 'git worktree add "$_WT_DIR" HEAD --detach' in content

    def test_target_branch_worktree(self):
        """With target_branch, worktree fetches and checks out that branch."""
        _, runner_path = build_runner_script(
            session_name="task-oppy-test-456",
            working_dir="/tmp/repo",
            prompt="do stuff",
            target_branch="card-5-sudoers-feature",
        )
        with open(runner_path) as f:
            content = f.read()

        # Should fetch the target branch
        assert 'git fetch origin "card-5-sudoers-feature"' in content
        # Should try origin/branch first, then local branch, then HEAD fallback
        assert 'git worktree add "$_WT_DIR" "origin/card-5-sudoers-feature"' in content
        assert 'git worktree add "$_WT_DIR" "card-5-sudoers-feature"' in content
        assert 'git worktree add "$_WT_DIR" HEAD --detach' in content
        # Should NOT use the default clade/ branch for worktree creation
        assert 'git worktree add "$_WT_DIR" -b "clade/' not in content

    def test_no_working_dir_skips_worktree(self):
        """Without working_dir, no worktree logic is generated."""
        _, runner_path = build_runner_script(
            session_name="task-oppy-test-789",
            working_dir=None,
            prompt="do stuff",
            target_branch="some-branch",
        )
        with open(runner_path) as f:
            content = f.read()

        assert "worktree" not in content.lower()
        assert "git fetch" not in content

    def test_target_branch_logged(self):
        """Target branch should be logged for debugging."""
        _, runner_path = build_runner_script(
            session_name="task-oppy-test-log",
            working_dir="/tmp/repo",
            prompt="do stuff",
            target_branch="my-feature",
        )
        with open(runner_path) as f:
            content = f.read()

        assert "target_branch=my-feature" in content
