# Illustrated explainers

Use this approach for illustrated flows, software architecture, component anatomy, and other system diagrams. Represent steps and components with recognizable objects whose contents or arrangement explain their roles. Preserve the actual sequence, branches, and dependencies. Abstract decisions can still use simple nodes and connectors.

## Visual grammar

- Draw a screen journey as one connected technical illustration, readable without advancing a step. Draw the landmarks the question names. Put intermediate steps in the response unless their appearance matters too. At 736px, three generous drawings fit with a full arrow between each pair. If more stages are essential, let the route turn into another row. Use the object's own outline and proportions before projecting it, so a phone stays tall and a component keeps its distinctive shape. For a landscape screen, the construction example uses a 174 × 96 face under `matrix(1 .25 -.55 .68 66 16)` inside `viewBox="0 0 260 156"`. Scale the whole SVG to its column so the slanted corners and side face stay inside the viewport. Replace the internal marks to identify the stage. Use a silhouette and action stripe where someone chooses an item, summary lines where they review it, or a check and number where it is confirmed. Caption each plate with its stage name and one short cue someone can see. Use the SVG connector below between each pair of screens. Center it on the screen drawings and put their captions in a separate row below. At narrow widths reflow the same small plates down one connector lane with the cues beside them. Actions inside a sketch are identifying marks.
- Draw a few generous, precise objects on the open host surface. Give each meaningful internal structure: a form with fields, a service with connected operations or ports, storage with organized records, a document with paragraph lines and citation marks, or a sheet with cells. Make the objects distinguishable before reading their labels. Avoid front-facing text boxes, generic speech bubbles, and empty labeled slabs. Keep explanatory sentences in the response; use supplied facts and do not invent measurements, budgets, or business facts to fill the objects.
- Default to a consistent shallow oblique projection with thin opaque faces, precise internal marks, and short external labels. A useful SVG transform is `matrix(1 .25 -.55 .68 tx ty)`. Apply it to the object and its internal drawing together. Keep external labels and connectors in screen space. Use a front view only when the user requests it or perspective would obscure essential information.
- Keep faces opaque using `var(--background)`. Mix `var(--foreground)` into that background for side faces (about 6%), structural edges (45%), and internal rules (20%). Do not lower opacity on the whole object: hidden edges must not show through. Use about 0.8–1px non-scaling strokes and only 2–3 screen pixels of apparent thickness. One important internal mark may use the full foreground or a meaningful series color.
- Use short, flat labels outside the projected shapes, at the normal text size. A system monospace face can give technical labels their character; this is a local exception to the usual prose font. Keep smaller captions secondary. Avoid tilted text, giant headings, numbered badges, heavy shadows, translucent overlaps, and repeated descriptions.
- Connect the facing edges of the drawn objects. At each end leave 10–12px of air, then run the shaft across the gap. Give a directed link an open head. Use a plain line for an undirected connection. Treat the full label/caption rectangle as an obstacle. For citations or other cross-references, matching reference marks on the two objects often communicate more clearly than a long return arrow. Use a return path only with a reserved lane that reaches the objects without crossing labels.
- Prefer a compact horizontal composition at normal width. For an exploded stack, offset layers only enough to expose their contents and route a few relationships along the open edge. On narrow screens, put compact objects beside wrapping labels in successive rows: at 320px, reserve about 140px for geometry, at least 16px of clear space, then labels. Scale only geometry into its column; keep labels at the normal host text size (12–14 screen pixels at the default scale). Let each row grow to fit its wrapped label, and keep the identifying mark large enough to recognize at phone size. Keep connectors in the geometry column or a separate gutter. Preserve relationships while abbreviating internal marks; do not stack full-size, text-filled desktop panels into a long poster. Set the SVG viewBox from the measured container width and redraw with ResizeObserver.
- Allocate space after projection: a local rectangle `w` by `h` spans `[-.55*h, w]` horizontally and `[0, .25*w + .68*h]` vertically. The negative left bound matters: translating the local origin to the column's left edge clips the object. Project all corners including stacked offsets and side faces, then find their combined `minX`, `maxX`, `minY`, `maxY`. To fit a column of width `W` starting at `(left, top)`, use `s = Math.min(1, W/(maxX-minX))`, `tx = left-s*minX`, `ty = top-s*minY`, and `matrix(s, .25*s, -.55*s, .68*s, tx, ty)`. Start labels at least 16px beyond the resulting right bound, wrapping within the remaining width. Keep external text in `--foreground` or `--muted-foreground`; never reuse the pale structural stroke color for text.

## Connecting two objects

Draw the connector as part of the illustration. A typeset arrow sits on a text baseline and leaves most of the gap empty. Budget the links before dividing the remaining width among the drawings. For three landmarks, use `grid-template-columns: 1fr 60px 1fr 60px 1fr` for the artwork row. Measure from the painted edges along the shaft. A plate's SVG can contain empty space, so extend the line into that space to reach the 10–12px clearance. This SVG fills that track. It has no viewBox, so one unit stays one CSS pixel. The same 8px head turns downward when the objects stack.

```html
<style>
  .flow-link { display: block; width: 100%; min-width: 48px; height: 16px; align-self: center; color: color-mix(in srgb, var(--foreground) 70%, var(--background)); }
  .flow-link .down { display: none; }
  @media (max-width: 560px) {
    .flow-link { grid-column: 1; height: 40px; }
    .flow-link .across { display: none; }
    .flow-link .down { display: inline; }
  }
</style>
<svg class="flow-link" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5">
  <defs>
    <marker id="flow-head" orient="auto" markerUnits="userSpaceOnUse" refX="8" refY="5" markerWidth="10" markerHeight="10">
      <path d="M1 1L8 5 1 9" stroke-linecap="round" stroke-linejoin="round"/>
    </marker>
  </defs>
  <line class="across" x1="1" y1="50%" x2="99%" y2="50%" marker-end="url(#flow-head)"/>
  <line class="down" x1="50%" y1="1" x2="50%" y2="98%" marker-end="url(#flow-head)"/>
</svg>
```

Define the marker once per illustration and reuse it on each link. Match the media query to the layout breakpoint. For a shared SVG scene, place the same marker on a path between the projected edges. At phone width, follow the column of objects. Run the shaft through the open space between their faces even when a caption makes a row taller.

## Small construction example

This illustrates one sheet, not a mandatory layout. Its cells are part of the object. Add task-specific contents and relationships; do not copy a sheet for every kind of component.

```html
<svg viewBox="0 0 260 156" role="img" aria-label="A sheet with rows and columns">
  <style>
    .technical-sheet { --edge: color-mix(in srgb, var(--foreground) 45%, var(--background)); --rule: color-mix(in srgb, var(--foreground) 20%, var(--background)); }
    .technical-sheet path { vector-effect: non-scaling-stroke; stroke-linejoin: round; }
  </style>
  <g class="technical-sheet" transform="matrix(1 .25 -.55 .68 66 16)">
    <path d="M0 96H174l2 3.6H2Z M174 0l2 3.6v96l-2-3.6Z" fill="color-mix(in srgb,var(--foreground) 6%,var(--background))" stroke="var(--edge)" stroke-width=".8"/>
    <path d="M0 0H174V96H0Z" fill="var(--background)" stroke="var(--edge)" stroke-width=".8"/>
    <path d="M12 12H162V30H12Z" fill="color-mix(in srgb,var(--foreground) 6%,var(--background))"/>
    <path d="M12 12H162V84H12Z M12 30H162 M12 48H162 M12 66H162 M62 12V84 M112 12V84" fill="none" stroke="var(--rule)" stroke-width=".8"/>
  </g>
  <text x="130" y="144" text-anchor="middle" fill="var(--foreground)" style="font-family:ui-monospace,monospace">Source records</text>
</svg>
```

When testing, inspect light and dark at 736px and 320–360px. Check silhouette, readable labels, opaque overlaps, and connector clearance in the rendered result, not just source coordinates.
