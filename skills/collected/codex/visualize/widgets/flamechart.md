# Sampled CPU flame chart

Use `<viz-flame-chart>` for chronological stack samples from one thread. Prefer wide mode.

```html
<viz-flame-chart id="profile" title="Render order details" thread-name="Main thread" description="CPU samples every 1 ms"></viz-flame-chart>
<script type="module">
  import "https://persistent.oaistatic.com/plugins/visualize/widgets/1.0.59/flame-chart.js";

  const profile = document.getElementById("profile");
  profile.frames = [
    { id: "render", name: "renderOrder", category: "JavaScript" },
    { id: "layout", name: "layoutRows", category: "Layout" },
    { id: "paint", name: "paintRows", category: "Paint" },
  ];
  profile.samples = [
    { stack: ["render", "layout"], durationMs: 1 },
    { stack: ["render", "layout"], durationMs: 1 },
    { stack: ["render"], durationMs: 1 },
    { stack: ["render", "paint"], durationMs: 1 },
    { stack: [], durationMs: 1 },
  ];
</script>
```

## API

Set optional `title`, `description`, and `thread-name` attributes for context. Assign `.frames` and `.samples` to render; replace either array to update it.

Each object in `.frames` describes one function:

| Field | Meaning |
| --- | --- |
| `id` | Required unique string, referenced by samples. |
| `name` | Required function label. |
| `category` | Optional category used to group colors. |

Each object in `.samples` describes one consecutive time interval:

| Field | Meaning |
| --- | --- |
| `stack` | Required array of frame IDs in root-to-leaf order. Every ID must appear in `.frames`. An empty array records idle time. |
| `durationMs` | Required positive interval represented by the sample, in milliseconds. |

Samples are chronological and laid out consecutively. Preserve their order instead of sorting by duration. In the example, `renderOrder` has 4 ms of inclusive time and 1 ms of self time; the final millisecond is idle. These are sampled estimates rather than exact call timings.

The viewer supplies search, zoom, panning, a range overview, and a function table. For persistence, read `.viewState` or save `event.detail.state` from `viz-state-change`, then assign it back to `.viewState`. The event also includes `selection`, either `null` or `{ callId, frameId, name, startMs, durationMs, selfMs }`; durations describe the selected contiguous call occurrence.

Rendering happens automatically after assignment. `.ready` is an optional promise for code that must wait for the current render. Invalid input appears inline and emits `viz-error` with `event.detail.message`.

Supply at most 20,000 frames and 20,000 samples, with at most 128 frames per stack and 100,000 stack entries across all samples.
