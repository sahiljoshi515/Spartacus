#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import sys

DEFAULT_STORE_PATH = os.path.expanduser("~/.taskman/tasks.json")


def get_store_path(args):
    store_arg = getattr(args, "store", None)
    if store_arg:
        return store_arg
    env_store = os.environ.get("TASKMAN_STORE")
    if env_store:
        return env_store
    return DEFAULT_STORE_PATH


def load_data(store_path):
    if not os.path.exists(store_path):
        return {"next_id": 1, "tasks": []}
    try:
        with open(store_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"next_id": 1, "tasks": []}
            if "next_id" not in data or "tasks" not in data:
                data.setdefault("next_id", 1)
                data.setdefault("tasks", [])
            return data
    except Exception:
        return {"next_id": 1, "tasks": []}


def save_data(store_path, data):
    dir_name = os.path.dirname(os.path.abspath(store_path))
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def cmd_add(args):
    store_path = get_store_path(args)
    data = load_data(store_path)
    title = " ".join(args.title) if isinstance(args.title, list) else str(args.title)
    title = title.strip()
    if not title:
        print("Error: Task title cannot be empty.", file=sys.stderr)
        sys.exit(1)

    task_id = data["next_id"]
    data["next_id"] += 1

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

    task = {
        "id": task_id,
        "title": title,
        "status": "pending",
        "priority": args.priority.lower() if args.priority else "medium",
        "created_at": now,
        "due": args.due if args.due else "",
        "tags": tags,
        "completed_at": None,
    }
    data["tasks"].append(task)
    save_data(store_path, data)
    print(f"Created task {task_id}: '{title}'")


def cmd_list(args):
    store_path = get_store_path(args)
    data = load_data(store_path)
    tasks = data.get("tasks", [])

    if not tasks:
        print("No tasks found.")
        return

    # Status filtering
    status_filter = getattr(args, "status", None)
    if args.all:
        filtered_tasks = list(tasks)
    elif status_filter:
        if status_filter == "all":
            filtered_tasks = list(tasks)
        else:
            filtered_tasks = [t for t in tasks if t.get("status") == status_filter]
    else:
        # Default behavior: show pending tasks
        filtered_tasks = [t for t in tasks if t.get("status") == "pending"]

    # Tag filtering
    if getattr(args, "tag", None):
        target_tag = args.tag.lower()
        filtered_tasks = [
            t for t in filtered_tasks
            if any(target_tag == tag.lower() for tag in t.get("tags", []))
        ]

    if not filtered_tasks:
        print("No tasks found matching criteria.")
        return

    # Sorting
    sort_key = getattr(args, "sort", "id")
    if sort_key == "priority":
        prio_map = {"high": 0, "medium": 1, "low": 2}
        filtered_tasks.sort(key=lambda t: prio_map.get(t.get("priority", "medium").lower(), 9))
    elif sort_key == "due":
        filtered_tasks.sort(key=lambda t: t.get("due") or "9999-99-99")
    elif sort_key == "created":
        filtered_tasks.sort(key=lambda t: t.get("created_at", ""))
    else:  # id
        filtered_tasks.sort(key=lambda t: t.get("id", 0))

    headers = ["ID", "Status", "Priority", "Title", "Due", "Tags"]
    rows = []
    for t in filtered_tasks:
        status_str = "[x] done" if t.get("status") == "done" else "[ ] pending"
        due_str = t.get("due") or "-"
        tags_str = ", ".join(t.get("tags", [])) if t.get("tags") else "-"
        rows.append([
            str(t.get("id", "")),
            status_str,
            t.get("priority", "medium"),
            t.get("title", ""),
            due_str,
            tags_str,
        ])

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    header_line = " | ".join(headers[i].ljust(col_widths[i]) for i in range(len(headers)))
    separator_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))

    print(header_line)
    print(separator_line)
    for row in rows:
        line = " | ".join(row[i].ljust(col_widths[i]) for i in range(len(row)))
        print(line)


def cmd_done(args):
    store_path = get_store_path(args)
    data = load_data(store_path)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    has_error = False
    updated_count = 0

    for task_id in args.ids:
        found = False
        for task in data.get("tasks", []):
            if task.get("id") == task_id:
                task["status"] = "done"
                task["completed_at"] = now
                print(f"Marked task {task_id} as completed.")
                found = True
                updated_count += 1
                break
        if not found:
            print(f"Error: Task {task_id} not found.", file=sys.stderr)
            has_error = True

    if updated_count > 0:
        save_data(store_path, data)

    if has_error:
        sys.exit(1)


def cmd_rm(args):
    store_path = get_store_path(args)
    data = load_data(store_path)
    tasks = data.get("tasks", [])

    ids_to_remove = set(args.ids)
    existing_ids = {t.get("id") for t in tasks}

    has_error = False
    for task_id in args.ids:
        if task_id not in existing_ids:
            print(f"Error: Task {task_id} not found.", file=sys.stderr)
            has_error = True

    new_tasks = [t for t in tasks if t.get("id") not in ids_to_remove]
    removed_count = len(tasks) - len(new_tasks)

    if removed_count > 0:
        data["tasks"] = new_tasks
        save_data(store_path, data)
        for task_id in args.ids:
            if task_id in existing_ids:
                print(f"Deleted task {task_id}.")

    if has_error:
        sys.exit(1)


def cmd_stats(args):
    store_path = get_store_path(args)
    data = load_data(store_path)
    tasks = data.get("tasks", [])

    total = len(tasks)
    if total == 0:
        print("Task Statistics:")
        print("Total tasks:     0")
        print("Pending tasks:   0")
        print("Completed tasks: 0")
        print("Completion rate: 0.0%")
        return

    completed = sum(1 for t in tasks if t.get("status") == "done")
    pending = total - completed
    rate = (completed / total) * 100.0

    high_prio = sum(1 for t in tasks if t.get("priority") == "high")
    med_prio = sum(1 for t in tasks if t.get("priority") == "medium")
    low_prio = sum(1 for t in tasks if t.get("priority") == "low")

    print("Task Statistics:")
    print(f"Total tasks:     {total}")
    print(f"Pending tasks:   {pending}")
    print(f"Completed tasks: {completed}")
    print(f"Completion rate: {rate:.1f}%")
    print("Priority breakdown:")
    print(f"  High:   {high_prio}")
    print(f"  Medium: {med_prio}")
    print(f"  Low:    {low_prio}")


def main():
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--store", "-s", default=argparse.SUPPRESS, help="Path to JSON store file"
    )

    parser = argparse.ArgumentParser(
        description="Taskman: Command-line task manager", parents=[parent_parser]
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")

    # add
    parser_add = subparsers.add_parser("add", help="Add a new task", parents=[parent_parser])
    parser_add.add_argument("title", nargs="+", help="Task title")
    parser_add.add_argument(
        "--priority",
        "-p",
        choices=["low", "medium", "high"],
        default="medium",
        help="Task priority (low, medium, high)",
    )
    parser_add.add_argument("--due", "-d", help="Due date (e.g. YYYY-MM-DD)")
    parser_add.add_argument("--tags", "-t", help="Comma-separated tags")

    # list
    parser_list = subparsers.add_parser(
        "list", help="List tasks in an aligned table", parents=[parent_parser]
    )
    parser_list.add_argument(
        "--all", "-a", action="store_true", help="Include completed tasks"
    )
    parser_list.add_argument(
        "--status", choices=["pending", "done", "all"], help="Filter by status"
    )
    parser_list.add_argument("--tag", help="Filter by tag")
    parser_list.add_argument(
        "--sort",
        choices=["id", "priority", "due", "created"],
        default="id",
        help="Sort order",
    )

    # done
    parser_done = subparsers.add_parser(
        "done", help="Mark task(s) as completed", parents=[parent_parser]
    )
    parser_done.add_argument("ids", nargs="+", type=int, help="Task ID(s) to mark as completed")

    # rm
    parser_rm = subparsers.add_parser(
        "rm", help="Remove task(s)", parents=[parent_parser]
    )
    parser_rm.add_argument("ids", nargs="+", type=int, help="Task ID(s) to remove")

    # stats
    parser_stats = subparsers.add_parser(
        "stats", help="Display task statistics", parents=[parent_parser]
    )

    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        sys.exit(0)

    if args.subcommand == "add":
        cmd_add(args)
    elif args.subcommand == "list":
        cmd_list(args)
    elif args.subcommand == "done":
        cmd_done(args)
    elif args.subcommand == "rm":
        cmd_rm(args)
    elif args.subcommand == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
