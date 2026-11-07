# Calendar

Use `<viz-calendar>` for dated events. Keep a single day at regular conversation width. Prefer wide mode for week and month views. The element supplies its own `.widget` surface and spacing.

## Day, week, and month

Include the module import before assigning events.

```html
<viz-calendar id="calendar-host" date="2026-09-08" start="11:00" end="14:00"></viz-calendar>
<script type="module">
  import "https://persistent.oaistatic.com/plugins/visualize/widgets/1.0.59/calendar.js";

  const calendar = document.getElementById("calendar-host");
  calendar.events = [
    { title: "Standup", start: "11:00", end: "11:30" },
    { title: "Focus time", start: "11:30", end: "13:00", tone: "green" },
    { title: "Design sync", start: "13:00", end: "14:00", video: true },
  ];
</script>
```

Set `view="week"` to compare times across seven days or `view="month"` to see events by date. Add a `date` to each event in multi-day views. Previous and next navigation works without custom handlers.

## Attributes

| Attribute | Meaning |
| --- | --- |
| `date` | Required anchor day as `YYYY-MM-DD`. Also supplies the date for undated events. |
| `view` | `day` (default), `week`, or `month`. |
| `start`, `end` | Visible hours in day and week views, as local `HH:MM`. Defaults to `09:00` and `17:00`. The end must be later than the start. |
| `time-zone` | Optional displayed zone label. Convert source timestamps to this zone before supplying dates and times; the calendar does not convert them. |
| `now` | Optional local `HH:MM` on the anchor day. Draws the current-time marker and dims past events. Supply only when the time is verified. |
| `lang` | Optional locale for labels and the first day of the week. Defaults to the document's locale, then `en`. |
| `interactive` | Boolean attribute enabling event selection by click or keyboard. Omit unless handling selection. |
| `empty-label` | Optional text for an empty view. By default, an empty calendar shows its grid without a message. |
| `events` | Alternative JSON event array. Prefer the JavaScript `.events` property for data from a source. |

## Event data

Assign an array of up to 200 objects to `.events`. Replace the array to update the view.

| Field | Meaning |
| --- | --- |
| `title` | Required event label. |
| `start`, `end` | Required local `HH:MM` times. The end must be later than the start; `24:00` is allowed for the end. Split events crossing midnight into dated segments. |
| `date` | Optional `YYYY-MM-DD`, defaulting to the calendar's anchor day. |
| `id` | Optional caller-owned string or number, preserved in selection events. |
| `tone` | Optional `blue` (default), `green`, `red`, `orange`, `purple`, or `yellow`. |
| `detail` | Optional secondary text. |
| `video` | Optional boolean showing a video-call icon. |

Event tooltips are supplied automatically, including the full title, time, and detail. Do not add duplicate tooltips.

With `interactive` enabled, listen for `eventselect`: `event.detail.event` is the original input object and `event.detail.index` is its index in the input array.

For a bulk update, `.config` accepts `date`, `view`, `start`, `end`, `now`, `timeZone`, `lang`, `emptyLabel`, `interactive`, and `events`; omitted options return to their defaults. Setting `.events = undefined` restores the JSON attribute as the data source. Rendering is synchronous; no readiness call is needed.

## Offline day view

The bundled `<viz-calendar>` renders a single day without a module import. Keep it at regular conversation width; it supplies its own `.widget` surface and spacing.

```html
<viz-calendar id="calendar-day" date="2026-09-08" start="11:00" end="14:00"></viz-calendar>
<script>
  document.getElementById("calendar-day").events = [
    { title: "Standup", start: "11:00", end: "11:30" },
    { title: "Design sync", start: "13:00", end: "14:00", video: true },
  ];
</script>
```

Set `date` to `YYYY-MM-DD` and `start`/`end` to local `HH:MM` times; the visible range defaults to `09:00`–`17:00`. Optional attributes are `now` for a verified current-time marker, `time-zone` for a display label, `lang` for locale, and `empty-label` for empty-state text. Convert source timestamps before supplying local dates and times.

Assign up to 200 events to `.events`, replacing the array to update. Each event needs `title`, `start`, and `end`, with the end later than the start. Optional fields are `id`, `detail`, `video` (boolean), and `tone` (`blue`, `green`, `red`, `orange`, `purple`, or `yellow`). Times use `HH:MM`; `24:00` is allowed for the end. An `events` JSON attribute is also supported. Tooltips are supplied automatically.

Add `interactive` to handle selection, then listen for `eventselect`; `event.detail.event` is the original event and `event.detail.index` its array index.

## Migrating a saved day view

To move a saved day view to the hosted version, add the `calendar.js` import shown above. The host then omits the bundled implementation. Keep the same tag, attributes, event data, and selection listeners.
