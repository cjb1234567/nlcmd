from unittest.mock import patch

import pytest
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from nlcmd.cron.scheduler import (
    ThinkingTask,
    TaskManager,
    _escape_toml_string,
    _dump_tasks_to_toml,
    parse_trigger,
)


class TestEscapeTomlString:
    def test_escape_backslash(self):
        assert _escape_toml_string("path\\to\\file") == "path\\\\to\\\\file"

    def test_escape_quote(self):
        assert _escape_toml_string('say "hello"') == 'say \\"hello\\"'

    def test_escape_newline(self):
        assert _escape_toml_string("line1\nline2") == "line1\\nline2"

    def test_escape_combined(self):
        assert _escape_toml_string('a\\b"c\nd') == 'a\\\\b\\"c\\nd'

    def test_no_escape_needed(self):
        assert _escape_toml_string("simple text") == "simple text"


class TestDumpTasksToToml:
    def test_single_task(self):
        tasks = [
            ThinkingTask(name="test", prompt="do something", schedule="every 10 seconds")
        ]
        result = _dump_tasks_to_toml(tasks)
        assert 'name = "test"' in result
        assert 'prompt = "do something"' in result
        assert 'schedule = "every 10 seconds"' in result
        assert "enabled = true" in result

    def test_multiple_tasks(self):
        tasks = [
            ThinkingTask(name="task1", prompt="prompt1", schedule="daily"),
            ThinkingTask(name="task2", prompt="prompt2", schedule="every 1 hour", enabled=False),
        ]
        result = _dump_tasks_to_toml(tasks)
        assert result.count("[[tasks]]") == 2
        assert "task1" in result
        assert "task2" in result
        assert "enabled = false" in result

    def test_empty_tasks(self):
        result = _dump_tasks_to_toml([])
        assert result == ""

    def test_task_with_special_chars(self):
        tasks = [
            ThinkingTask(name="test", prompt='say "hello"\\nworld', schedule="daily")
        ]
        result = _dump_tasks_to_toml(tasks)
        assert 'say \\"hello\\"\\\\nworld' in result


class TestThinkingTask:
    def test_default_enabled(self):
        task = ThinkingTask(name="test", prompt="prompt", schedule="daily")
        assert task.enabled is True

    def test_custom_enabled(self):
        task = ThinkingTask(name="test", prompt="prompt", schedule="daily", enabled=False)
        assert task.enabled is False

    def test_model_dump(self):
        task = ThinkingTask(name="test", prompt="prompt", schedule="every 5 minutes")
        data = task.model_dump()
        assert data["name"] == "test"
        assert data["prompt"] == "prompt"
        assert data["schedule"] == "every 5 minutes"
        assert data["enabled"] is True


class TestParseTrigger:
    def test_daily(self):
        trigger = parse_trigger("daily")
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.days == 1

    def test_every_seconds(self):
        trigger = parse_trigger("every 10 seconds")
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.seconds == 10

    def test_every_minutes(self):
        trigger = parse_trigger("every 5 minutes")
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 300

    def test_every_hours(self):
        trigger = parse_trigger("every 2 hours")
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 7200

    def test_every_days(self):
        trigger = parse_trigger("every 3 days")
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.days == 3

    def test_cron_expression(self):
        trigger = parse_trigger("cron: */5 * * * *")
        assert isinstance(trigger, CronTrigger)

    def test_case_insensitive(self):
        trigger1 = parse_trigger("DAILY")
        trigger2 = parse_trigger("EVERY 10 SECONDS")
        assert isinstance(trigger1, IntervalTrigger)
        assert isinstance(trigger2, IntervalTrigger)

    def test_plural_optional(self):
        trigger1 = parse_trigger("every 1 second")
        trigger2 = parse_trigger("every 1 seconds")
        assert isinstance(trigger1, IntervalTrigger)
        assert isinstance(trigger2, IntervalTrigger)

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported schedule format"):
            parse_trigger("invalid format")


class TestTaskManager:
    @pytest.fixture
    def temp_workspace(self, tmp_path):
        with patch("nlcmd.cron.scheduler.config.WORKSPACE", tmp_path):
            yield tmp_path

    def test_ensure_config_creates_directory(self, temp_workspace):
        manager = TaskManager()
        assert manager.cron_dir.exists()
        assert manager.config_file.exists()

    def test_load_empty_tasks(self, temp_workspace):
        manager = TaskManager()
        tasks = manager.load_tasks()
        assert tasks == []

    def test_add_task(self, temp_workspace):
        manager = TaskManager()
        manager.add_task("test_task", "test prompt", "every 10 seconds")
        
        tasks = manager.load_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "test_task"
        assert tasks[0].prompt == "test prompt"
        assert tasks[0].schedule == "every 10 seconds"
        assert tasks[0].enabled is True

    def test_add_duplicate_task(self, temp_workspace, capsys):
        manager = TaskManager()
        manager.add_task("test_task", "prompt1", "daily")
        manager.add_task("test_task", "prompt2", "every 1 hour")
        
        tasks = manager.load_tasks()
        assert len(tasks) == 1
        assert tasks[0].prompt == "prompt1"

    def test_remove_task(self, temp_workspace):
        manager = TaskManager()
        manager.add_task("task1", "prompt1", "daily")
        manager.add_task("task2", "prompt2", "every 1 hour")
        
        manager.remove_task("task1")
        
        tasks = manager.load_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "task2"

    def test_remove_nonexistent_task(self, temp_workspace, capsys):
        manager = TaskManager()
        manager.add_task("task1", "prompt1", "daily")
        
        manager.remove_task("nonexistent")
        
        tasks = manager.load_tasks()
        assert len(tasks) == 1

    def test_save_and_load_preserves_data(self, temp_workspace):
        manager = TaskManager()
        
        tasks_to_save = [
            ThinkingTask(name="task1", prompt="中文提示", schedule="daily"),
            ThinkingTask(name="task2", prompt="prompt with 'quotes'", schedule="every 30 minutes", enabled=False),
        ]
        manager.save_tasks(tasks_to_save)
        
        loaded_tasks = manager.load_tasks()
        assert len(loaded_tasks) == 2
        assert loaded_tasks[0].name == "task1"
        assert loaded_tasks[0].prompt == "中文提示"
        assert loaded_tasks[1].enabled is False

    def test_load_invalid_toml(self, temp_workspace):
        manager = TaskManager()
        
        with open(manager.config_file, "w", encoding="utf-8") as f:
            f.write("invalid [[toml")
        
        tasks = manager.load_tasks()
        assert tasks == []
