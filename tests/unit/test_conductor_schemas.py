"""Unit tests for conductor tool schemas."""

from clade.conductor.schemas import TOOLS


class TestSchemas:
    def test_all_tools_have_required_fields(self):
        """Every tool must have name, description, and input_schema."""
        for tool in TOOLS:
            assert "name" in tool, f"Tool missing name: {tool}"
            assert "description" in tool, f"Tool {tool['name']} missing description"
            assert "input_schema" in tool, f"Tool {tool['name']} missing input_schema"
            assert tool["input_schema"]["type"] == "object", (
                f"Tool {tool['name']} input_schema type must be 'object'"
            )

    def test_tool_names_unique(self):
        names = [t["name"] for t in TOOLS]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_expected_tools_present(self):
        """Verify the conductor has all the tools it needs."""
        names = {t["name"] for t in TOOLS}
        expected = {
            "delegate_task",
            "check_worker_health",
            "list_worker_tasks",
            "send_message",
            "check_mailbox",
            "read_message",
            "browse_feed",
            "unread_count",
            "list_tasks",
            "get_task",
            "update_task",
            "retry_task",
            "kill_task",
            "deposit_morsel",
            "list_morsels",
            "get_morsel",
            "list_board",
            "get_card",
            "create_card",
            "move_card",
            "update_card",
            "archive_card",
            "list_trees",
            "get_tree",
            "search",
        }
        missing = expected - names
        assert not missing, f"Missing tools: {missing}"

    def test_required_params(self):
        """Check that tools with required params have them in the schema."""
        tools_by_name = {t["name"]: t for t in TOOLS}

        # delegate_task requires brother and prompt
        dt = tools_by_name["delegate_task"]
        assert "brother" in dt["input_schema"]["required"]
        assert "prompt" in dt["input_schema"]["required"]

        # get_task requires task_id
        gt = tools_by_name["get_task"]
        assert "task_id" in gt["input_schema"]["required"]

        # send_message requires recipients and body
        sm = tools_by_name["send_message"]
        assert "recipients" in sm["input_schema"]["required"]
        assert "body" in sm["input_schema"]["required"]
