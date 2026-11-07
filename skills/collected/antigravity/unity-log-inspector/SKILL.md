---
name: unity-log-inspector
description: >-
  Use this skill to inspect, filter, and extract high-signal diagnostics from Unity Editor logs (Editor.log, Editor-prev.log, upm.log), including C# compilation errors, unhandled exceptions, and test runner exit statuses.
---

# Unity Log Inspector

This skill provides an automated diagnostic tool (`scripts/inspect_unity_logs.py`) to parse, filter, and summarize Unity editor logs, test runs, and package manager logs without wading through thousands of lines of engine boilerplate.

## Key Capabilities

1. **Automatic Log Resolution**: Automatically selects `Logs/Editor.log` (if active and non-empty) or `Logs/Editor-prev.log` (most recent run), with fallback to system AppData logs.
2. **Noise Suppression**: Strips licensing handshakes, Direct3D device probes, memory allocator setups, and asset database remapping logs.
3. **Targeted Extraction**:
   - `--errors`: Extracts compilation errors, unhandled exceptions, and fatal assertions.
   - `--compilation`: Isolates C# compilation errors across all assemblies (including tests and authoring).
   - `--tests`: Extracts test runner exit codes and execution summaries.
   - `--tail <N>`: Shows the last N meaningful log events (default: 30).
   - `--list`: Lists all discovered log files in the project and user AppData.

---

## Common Usage Commands

Helper script path:
`.agents/skills/unity-log-inspector/scripts/inspect_unity_logs.py`

```powershell
# 1. Quick diagnostic summary of the most recent Unity run:
python .agents/skills/unity-log-inspector/scripts/inspect_unity_logs.py

# 2. Extract strictly errors and unhandled exceptions:
python .agents/skills/unity-log-inspector/scripts/inspect_unity_logs.py --errors

# 3. Check for C# compilation errors (especially when tests fail before execution):
python .agents/skills/unity-log-inspector/scripts/inspect_unity_logs.py --compilation

# 4. Check test runner exit status and command line:
python .agents/skills/unity-log-inspector/scripts/inspect_unity_logs.py --tests

# 5. List all available log files:
python .agents/skills/unity-log-inspector/scripts/inspect_unity_logs.py --list

# 6. Inspect a specific log file (e.g. Editor-prev.log or upm.log):
python .agents/skills/unity-log-inspector/scripts/inspect_unity_logs.py --file Logs/Editor-prev.log
```
