# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

(Note: context-mode MCP routing rules are injected by the context-mode plugin's SessionStart hook every session — they are not duplicated here.)

## What this is

Single-script project: `build_vltava_labe.py` converts Czech inland S-57/IENC chart cells (Vltava + Labe rivers, files like `9D7VL047.000`, `9D7EL726.000`) into a transparent raster overlay tile database for OsmAnd. Not a git repository. No tests, lint, or build system. All code, comments, and log messages are in Czech — keep user-facing strings in Czech.

## Running

The script requires PyQGIS + Qt + GDAL's S-57 driver and **only runs inside the QGIS Python Console** (Plugins → Python Console):

```python
exec(open(r"C:\Users\Lukas\Scripts\mapy_vltava_labe\build_vltava_labe.py", encoding="utf-8").read())
```

Plain `python` on this machine fails (no standalone Python/GDAL). To debug layer loading, check `output/S57_layers_report.txt` — it lists which S-57 layers GDAL actually sees in each `*.000` cell.

## Configuration

`config_example.txt` is **not read by the script** (vestige of an older version). Edit the constants at the top of `build_vltava_labe.py` directly:

- `INPUT_DIR` / `OUTPUT_DIR` — resolved relative to the script's own location (`input/`, `output/`).
- `MIN_ZOOM = 10`, `MAX_ZOOM = 16` — 16 is deliberate; raising to 17–18 dramatically increases tile count and render time.

## Data layout

- `input/*.000` — S-57 cells picked up by the build. The glob is **non-recursive**.
- `input/later/` — archive of additional cells **ignored by the build**; move cells up into `input/` to include them.
- `VL01.zip`, `VL02.zip`, `EL01*.zip`, `EL02.zip`, `EL03.zip`, `9D7EL726.zip` — original source chart archives.
- `Vltava_Labe_OsmAnd*.zip` — previously built outputs.
- `README_CZ.md` documents an older directory layout (`Vltava_Labe_OsmAnd\input\`); the actual code uses `input/` beside the script.

## Pipeline (`run()` in build_vltava_labe.py)

1. `find_s57_cells()` globs `input/*.000`; `write_layer_report()` writes the layer report.
2. `ogr_layers()` discovers available layers per cell; loads only layers in `ALL_WANTED` (flattened from `LAYER_GROUPS`) that actually exist — missing layers are skipped, not an error.
3. `load_qgis_layer()` opens each cell via QGIS's OGR provider with `UPDATES=APPLY`, `SPLIT_MULTIPOINT=ON`, `ADD_SOUNDG_DEPTH=ON` (individual SOUNDG points get a `DEPTH` attribute).
4. `style_layer()` applies simple QGIS renderer styles per layer group (depth, buoys, beacons, lights, fairway, anchor, harbour, moles, obstacles, bridges, locks, shore).
5. Saves `Vltava_Labe_review.qgz` so the loaded S-57 content can be inspected in QGIS.
6. `transform_project_extent_to_4326()` computes the combined geographic extent; tile range per zoom comes from `qgs_extent_to_tile_range()`.
7. For each zoom 10–16, `render_tile()` renders a 256 px transparent PNG via `QgsMapRenderer`; `is_blank()` tiles are skipped; the rest go as BLOBs into `init_osmand_db()`'s `tiles` table, committing every 8 tile columns.

The output `Vltava_Labe.sqlitedb` uses standard OsmAnd settings: `ellipsoid = 0`, `inverted_y = 0`, `tilenumbering = ''` (normal spherical Web Mercator XYZ). Users add the file in OsmAnd as a raster overlay map.

Output is a visualization overlay only — not a replacement for Inland ECDIS.
