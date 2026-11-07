# Error stack trace

Use `<viz-stack-trace>` to show an error reported by an application. Supply the report as data; the error does not need to occur in the visualization's JavaScript.

```html
<viz-stack-trace id="failure"></viz-stack-trace>
<script type="module">
  import "https://persistent.oaistatic.com/plugins/visualize/widgets/1.0.59/stack-trace.js";

  const failure = document.getElementById("failure");
  failure.error = { name: "KeyError", message: "'total'" };
  failure.frames = [
    {
      name: "order_total", file: "orders.py", line: 2, column: 12,
      source: { startLine: 2, lines: ["    return order['total']"] },
    },
    { name: "show_order", file: "orders.py", line: 5, column: 12 },
  ];
</script>
```

## API

The example shows a Python orders service receiving a record without a total. Copy the name, message, and available frames from the source report. Optional `title` and `description` attributes add context.

- `.error`: `{ name, message, stack? }`, with string values. `stack` is optional raw traceback text.
- `.frames`: array of structured frames, most recent first. If omitted or empty, the viewer displays `.error.stack` verbatim. A captured JavaScript `Error` can also be assigned to `.error`.
- `.causes`: optional array of `{ name, message, frames, stack? }` objects for chained failures. Use an empty `frames` array when a cause has only raw stack text.

Each structured frame accepts:

| Field | Meaning |
| --- | --- |
| `name` | Required function or operation label. |
| `file` | Optional source file or path. |
| `line`, `column` | Optional one-based source position. |
| `source` | Optional `{ startLine, lines }`, where `startLine` is one-based and `lines` contains the original source strings. The viewer never fetches source files. |
| `kind` | Optional `app` or `runtime`. Consecutive runtime frames are grouped so the reader can expand them. |
| `async` | Optional boolean inserting an async-parent boundary before this frame. |
| `id` | Optional stable string for preserving selection across updates. Supplied IDs must be unique across the main stack and all causes. |

Replace the data properties to update the viewer. Structured frames take precedence over raw `stack` text; set `.frames = []` when switching to a raw-only report.

For state persistence, read `.viewState` or save `event.detail.state` from `viz-state-change`, then assign it back to `.viewState`. The state includes the selected frame and expanded groups. The event also includes `selection`, either `null` or `{ frameId, name, file?, line?, column? }`.

Rendering happens automatically after assignment. `.ready` is an optional promise for code that must wait for the current render. Invalid input appears inline and emits `viz-error` with `event.detail.message`.

Supply up to 2,000 frames per stack, 32 causes, and 500 source lines per frame.
