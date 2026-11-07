# Controls

Keep labeled native controls outside chart container; .viz-controls with .form-select/.form-range/.form-control; show values/units and wrap at narrow widths. Initialize defaults unconditionally; calculate/filter rows, mount once, assign full config and readouts on changes. Disable until import/handler ready or retain latest pending selection. Stable IDs/colors/intentional bounds/heights across changes. Calculated curves need explicit assumptions, valid input ranges and finite results; label model next to chart. input gives continuous slider feedback, change committed selections. Intl.NumberFormat.format(value), not calling the object. Validate default/changed calculations offline; compose text/requested tables or linked/saved state via applicable guides.

## Check the configurations your controls produce

When the page selects among fixed configs, store each complete config in its own `<script type="application/json" data-viz-chart>` block and read those blocks for the initial mount and updates. One `render.py --check` validates all of them. For calculated configs, serialize the output of the same config-building function used by the page at the default selection and representative changes, including range endpoints. Pass one file per selection in the same check.

```sh
python3 <skill-dir>/scripts/render.py /absolute/chart.html --check --chart-state initial.json --chart-state filtered.json
```

Read the counts for HTML and supplied states. A fragment can pass syntax checks with zero chart payloads checked. Each state file contains the exact chart or comparison config, including its real rows. The checks cover only the supplied configs. Check the control calculations and event wiring separately.
