# Taskman: CLI Task Manager

`taskman` is a simple, fast command-line task manager written in Python. It helps you manage tasks directly from your terminal with priority levels, due dates, tags, and formatted aligned table output.

Tasks are persisted locally in JSON format.

---

## Features

- **JSON Storage**: Stores tasks locally in JSON format.
- **Custom Store Location**: Use `--store <path>` or the `TASKMAN_STORE` environment variable to specify custom data store locations.
- **Formatted Table Output**: Automatically aligned table output for listing tasks.
- **Filtering & Sorting**: Filter tasks by status or tags, and sort by priority, due date, creation time, or task ID.
- **Task Statistics**: High-level completion rates and priority metrics.

---

## Installation & Usage

No external dependencies required! `taskman` uses Python 3 standard libraries (`argparse`, `json`, `datetime`, `os`, `sys`).

Make `taskman.py` executable or invoke via `python3`:

```bash
chmod +x taskman.py
./taskman.py --help
```

---

## Storage Location

By default, `taskman` saves task data to `~/.taskman/tasks.json`.

You can override the storage location in two ways:

1. **Environment Variable**: Set `TASKMAN_STORE`
   ```bash
   export TASKMAN_STORE=/path/to/my_tasks.json
   ```
2. **Command Line Option**: Pass `--store` or `-s`
   ```bash
   python3 taskman.py --store /path/to/my_tasks.json list
   ```

---

## Subcommands & Examples

### 1. `add`

Add a new task with a title, optional priority, due date, and tags.

```bash
# Add a basic task
python3 taskman.py add "Buy groceries"

# Add a task with options
python3 taskman.py add "Submit quarterly report" --priority high --due 2026-04-15 --tags work,finance
python3 taskman.py add "Schedule dentist appointment" -p low -d 2026-05-01 -t health
```

**Options:**
- `title` (positional): Task description
- `-p`, `--priority`: `low`, `medium` (default), or `high`
- `-d`, `--due`: Due date string (e.g. `YYYY-MM-DD`)
- `-t`, `--tags`: Comma-separated list of tags

---

### 2. `list`

Display tasks in an aligned ASCII table. By default, only pending tasks are displayed.

```bash
# List pending tasks
python3 taskman.py list

# List all tasks (including completed ones)
python3 taskman.py list --all

# Filter by status (pending, done, all)
python3 taskman.py list --status done

# Filter by tag
python3 taskman.py list --tag work

# Sort tasks by priority, due date, created date, or id
python3 taskman.py list --sort priority
python3 taskman.py list --sort due
```

**Output Example:**
```text
ID | Status      | Priority | Title                    | Due        | Tags
---+-------------+----------+--------------------------+------------+-------------
1  | [ ] pending | high     | Submit quarterly report  | 2026-04-15 | work, finance
2  | [ ] pending | low      | Schedule dentist appt    | 2026-05-01 | health
```

**Options:**
- `-a`, `--all`: Include completed tasks
- `--status`: Filter by `pending`, `done`, or `all`
- `--tag`: Filter tasks by tag name
- `--sort`: Sort output by `id` (default), `priority`, `due`, or `created`

---

### 3. `done`

Mark one or more tasks as completed by ID.

```bash
# Mark task #1 as completed
python3 taskman.py done 1

# Mark multiple tasks as completed
python3 taskman.py done 2 3
```

**Positional Arguments:**
- `ids`: One or more task IDs (integers)

---

### 4. `rm`

Delete one or more tasks from the store by ID.

```bash
# Remove task #1
python3 taskman.py rm 1

# Remove multiple tasks
python3 taskman.py rm 2 3
```

**Positional Arguments:**
- `ids`: One or more task IDs (integers) to remove

---

### 5. `stats`

Display a summary of task statistics, including total task count, completion rate, and priority breakdown.

```bash
python3 taskman.py stats
```

**Output Example:**
```text
Task Statistics:
Total tasks:     5
Pending tasks:   3
Completed tasks: 2
Completion rate: 40.0%
Priority breakdown:
  High:   1
  Medium: 2
  Low:    2
```

---

## Running Unit Tests

The test suite drives `taskman.py` using `subprocess` isolated inside temporary directories, ensuring the real store is never touched.

Run the test suite with verbose output:

```bash
python3 -m unittest test_taskman.py -v
```
