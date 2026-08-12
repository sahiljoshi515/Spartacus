#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest

TASKMAN_PY = os.path.abspath(os.path.join(os.path.dirname(__file__), "taskman.py"))


class TestTaskman(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = os.path.join(self.temp_dir.name, "store", "tasks.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_taskman(self, args, env=None):
        cmd = [sys.executable, TASKMAN_PY] + args
        custom_env = os.environ.copy()
        if "--store" not in args and "-s" not in args:
            custom_env["TASKMAN_STORE"] = self.store_path
        if env:
            custom_env.update(env)
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=custom_env,
        )
        return res

    def read_store_data(self):
        if not os.path.exists(self.store_path):
            return None
        with open(self.store_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_add_task(self):
        res = self.run_taskman(["add", "Buy groceries"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Created task 1: 'Buy groceries'", res.stdout)

        data = self.read_store_data()
        self.assertIsNotNone(data)
        self.assertEqual(len(data["tasks"]), 1)
        self.assertEqual(data["tasks"][0]["title"], "Buy groceries")
        self.assertEqual(data["tasks"][0]["status"], "pending")
        self.assertEqual(data["tasks"][0]["priority"], "medium")

    def test_add_task_with_options(self):
        custom_store = os.path.join(self.temp_dir.name, "custom.json")
        res = self.run_taskman([
            "--store", custom_store,
            "add", "Finish project proposal",
            "--priority", "high",
            "--due", "2026-12-31",
            "--tags", "work,urgent"
        ])
        self.assertEqual(res.returncode, 0)

        with open(custom_store, "r", encoding="utf-8") as f:
            data = json.load(f)
        task = data["tasks"][0]
        self.assertEqual(task["title"], "Finish project proposal")
        self.assertEqual(task["priority"], "high")
        self.assertEqual(task["due"], "2026-12-31")
        self.assertEqual(task["tags"], ["work", "urgent"])

    def test_list_aligned_table(self):
        self.run_taskman(["add", "Task One"])
        self.run_taskman(["add", "Task Two with a very long title"])
        res = self.run_taskman(["list"])
        self.assertEqual(res.returncode, 0)
        lines = res.stdout.strip().splitlines()
        self.assertGreaterEqual(len(lines), 3)
        self.assertIn("ID", lines[0])
        self.assertIn("Status", lines[0])
        self.assertIn("Title", lines[0])
        self.assertIn("-+-", lines[1])
        self.assertIn("Task One", res.stdout)
        self.assertIn("Task Two with a very long title", res.stdout)

    def test_list_status_filtering(self):
        self.run_taskman(["add", "Pending Task"])
        self.run_taskman(["add", "Task to Complete"])
        self.run_taskman(["done", "2"])

        res_default = self.run_taskman(["list"])
        self.assertIn("Pending Task", res_default.stdout)
        self.assertNotIn("Task to Complete", res_default.stdout)

        res_all = self.run_taskman(["list", "--all"])
        self.assertIn("Pending Task", res_all.stdout)
        self.assertIn("Task to Complete", res_all.stdout)

        res_done = self.run_taskman(["list", "--status", "done"])
        self.assertNotIn("Pending Task", res_done.stdout)
        self.assertIn("Task to Complete", res_done.stdout)

    def test_list_tag_filtering(self):
        self.run_taskman(["add", "Home chore", "-t", "home"])
        self.run_taskman(["add", "Work assignment", "-t", "work"])

        res = self.run_taskman(["list", "--tag", "home"])
        self.assertIn("Home chore", res.stdout)
        self.assertNotIn("Work assignment", res.stdout)

    def test_list_sorting(self):
        self.run_taskman(["add", "Low task", "-p", "low", "-d", "2026-05-01"])
        self.run_taskman(["add", "High task", "-p", "high", "-d", "2026-01-01"])

        res_prio = self.run_taskman(["list", "--sort", "priority"])
        high_idx = res_prio.stdout.find("High task")
        low_idx = res_prio.stdout.find("Low task")
        self.assertLess(high_idx, low_idx)

        res_due = self.run_taskman(["list", "--sort", "due"])
        high_due_idx = res_due.stdout.find("High task")
        low_due_idx = res_due.stdout.find("Low task")
        self.assertLess(high_due_idx, low_due_idx)

    def test_done_command(self):
        self.run_taskman(["add", "Write unit tests"])
        res = self.run_taskman(["done", "1"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Marked task 1 as completed.", res.stdout)

        data = self.read_store_data()
        self.assertEqual(data["tasks"][0]["status"], "done")
        self.assertIsNotNone(data["tasks"][0]["completed_at"])

    def test_rm_command(self):
        self.run_taskman(["add", "First Task"])
        self.run_taskman(["add", "Second Task"])
        res = self.run_taskman(["rm", "1"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Deleted task 1.", res.stdout)

        data = self.read_store_data()
        self.assertEqual(len(data["tasks"]), 1)
        self.assertEqual(data["tasks"][0]["id"], 2)

    def test_stats_command(self):
        res_empty = self.run_taskman(["stats"])
        self.assertIn("Total tasks:     0", res_empty.stdout)

        self.run_taskman(["add", "Task 1", "-p", "high"])
        self.run_taskman(["add", "Task 2", "-p", "medium"])
        self.run_taskman(["add", "Task 3", "-p", "low"])
        self.run_taskman(["done", "1"])

        res = self.run_taskman(["stats"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Total tasks:     3", res.stdout)
        self.assertIn("Pending tasks:   2", res.stdout)
        self.assertIn("Completed tasks: 1", res.stdout)
        self.assertIn("Completion rate: 33.3%", res.stdout)
        self.assertIn("High:   1", res.stdout)
        self.assertIn("Medium: 1", res.stdout)
        self.assertIn("Low:    1", res.stdout)

    def test_invalid_task_id(self):
        res_done = self.run_taskman(["done", "99"])
        self.assertNotEqual(res_done.returncode, 0)
        self.assertIn("Error: Task 99 not found.", res_done.stderr)

        res_rm = self.run_taskman(["rm", "99"])
        self.assertNotEqual(res_rm.returncode, 0)
        self.assertIn("Error: Task 99 not found.", res_rm.stderr)

    def test_empty_title_error(self):
        res = self.run_taskman(["add", "   "])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Error: Task title cannot be empty.", res.stderr)

    def test_done_multiple_tasks(self):
        self.run_taskman(["add", "Task 1"])
        self.run_taskman(["add", "Task 2"])
        res = self.run_taskman(["done", "1", "2"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Marked task 1 as completed.", res.stdout)
        self.assertIn("Marked task 2 as completed.", res.stdout)

        data = self.read_store_data()
        self.assertEqual(data["tasks"][0]["status"], "done")
        self.assertEqual(data["tasks"][1]["status"], "done")

    def test_rm_multiple_tasks(self):
        self.run_taskman(["add", "Task 1"])
        self.run_taskman(["add", "Task 2"])
        res = self.run_taskman(["rm", "1", "2"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Deleted task 1.", res.stdout)
        self.assertIn("Deleted task 2.", res.stdout)

        data = self.read_store_data()
        self.assertEqual(len(data["tasks"]), 0)

    def test_list_empty_store(self):
        res = self.run_taskman(["list"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("No tasks found.", res.stdout)

    def test_store_env_var(self):
        env_store = os.path.join(self.temp_dir.name, "env_store.json")
        res = self.run_taskman(["add", "Env Task"], env={"TASKMAN_STORE": env_store})
        self.assertEqual(res.returncode, 0)
        self.assertTrue(os.path.exists(env_store))
        with open(env_store, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["tasks"][0]["title"], "Env Task")


if __name__ == "__main__":
    unittest.main()
