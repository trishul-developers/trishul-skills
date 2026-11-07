# Request waterfall

Use `<viz-waterfall>` for timed spans from one request. Prefer wide mode.

```html
<viz-waterfall id="request" title="GET /api/orders/42"></viz-waterfall>
<script type="module">
  import "https://persistent.oaistatic.com/plugins/visualize/widgets/1.0.59/waterfall.js";

  const request = document.getElementById("request");
  request.spans = [
    { id: "http", name: "GET /api/orders/{id}", service: "orders-api", startMs: 0, durationMs: 120 },
    { id: "sql", parentId: "http", name: "SELECT orders", service: "postgres", startMs: 10, durationMs: 80 },
    { id: "cache", parentId: "http", name: "GET customer:7", service: "redis", startMs: 20, durationMs: 15 },
  ];
</script>
```

## API

Set optional `title` and `description` attributes for the heading and context. The HTML `id` is only needed to find the element. Assign `.spans` to render and replace the array to update it.

Each span has these fields:

| Field | Meaning |
| --- | --- |
| `id` | Required unique string. |
| `name` | Required operation label. |
| `startMs` | Required nonnegative offset from the beginning of the request, in milliseconds. |
| `durationMs` | Required nonnegative elapsed duration, in milliseconds. |
| `parentId` | Optional parent span ID; omit or use `null` for a root. Parents must exist and cannot form cycles. |
| `service` | Optional service name, used to group colors. |
| `status` | Optional `ok`, `warning`, or `error`. |
| `attributes` | Optional object of string, finite number, or boolean values shown in span details. |

The example request takes 120 ms. Its children overlap and cover 80 ms together, leaving 40 ms of direct time. The built-in controls switch between total and direct time, sort spans, search, and navigate the time range.

Optional properties:

- `.durationMs`: total time range, normally inferred from the latest span end. An explicit value must be positive and cover every span.
- `.criticalPath`: array of span IDs, if your tracing system recorded the dependency path. Otherwise the viewer estimates a path from timing and nesting; this is a visual estimate, not proof of causal dependencies.
- `.viewState`: read or restore the viewer's serializable selection, search, sorting, collapsed rows, and zoom state.

For state persistence, save `event.detail.state` from `viz-state-change` and assign it back to `.viewState`. The same event includes `selection`, either `null` or `{ spanId, name, startMs, durationMs, endMs }`.

Rendering happens automatically after assignment. `.ready` is an optional promise for code that must wait for the current render, such as a screenshot harness. Invalid input appears inline and emits `viz-error` with `event.detail.message`.

Supply at most 20,000 spans with at most 128 nesting levels. Each span may have up to 100 attributes.
