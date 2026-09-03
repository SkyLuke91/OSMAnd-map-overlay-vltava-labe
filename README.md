# Vltava + Labe → OsmAnd (S-57/IENC raster overlay)

`build_vltava_labe.py` converts Czech inland S-57/IENC chart cells (Vltava and
Labe rivers, files like `9D7VL047.000`, `9D7EL726.000`) into a transparent
raster overlay tile database for [OsmAnd](https://osmand.net/) — a SQLite tile
DB (`Vltava_Labe.sqlitedb`).

> ⚠️ The output is a visualization overlay only. It is not a replacement for
> Inland ECDIS and must not be used as the sole means of navigation.

[Česká verze](README_CZ.md)

## Requirements

- QGIS with PyQGIS, Qt, and GDAL's S-57 driver (tested on Windows).
- The script **only runs inside the QGIS Python Console** — there is no
  standalone Python/GDAL requirement or support.

## Setup

```bash
git clone https://github.com/SkyLuke91/mapy_vltava_labe.git
```

## Usage

1. In QGIS, open **Plugins → Python Console**.
2. Run:

```python
exec(open(r"C:\path\to\mapy_vltava_labe\build_vltava_labe.py", encoding="utf-8").read())
```

Output lands in `output/`:

- `Vltava_Labe.sqlitedb` — the OsmAnd tile database
- `Vltava_Labe_review.qgz` — QGIS project with the loaded S-57 layers for review
- `S57_layers_report.txt` — which S-57 layers GDAL actually sees in each `*.000` cell

In OsmAnd, add the file as a **raster overlay map**.

## Layout

```
build_vltava_labe.py     # the single main script
input/                   # S-57 cells *.000 (non-recursive glob)
input/later/             # archive of extra cells — IGNORED by the build
output/                  # sqlitedb + qgz + layer report
source of maps/          # original source chart archives (*.zip)
```

## How it works

1. `find_s57_cells()` globs `input/*.000` and writes the layer report.
2. Cells are opened via the OGR provider with `UPDATES=APPLY`,
   `SPLIT_MULTIPOINT=ON`, `ADD_SOUNDG_DEPTH=ON` (individual SOUNDG points get
   a `DEPTH` attribute).
3. Loaded layers: DEPCNT, SOUNDG, buoys and beacons (BOY*/BCN*), LIGHTS,
   FAIRWY, ACHARE, HRBPRT, MORFAC, OBSTRN, WRECKS, BRIDGE, GATCON, SLCONS,
   DAMCON, COALNE and more. Missing layers are skipped, not an error.
4. For each zoom 10–16, transparent 256 px PNG tiles are rendered; blank
   tiles (`is_blank()`) are skipped, the rest go into the SQLite DB.
5. Each layer gets a simple QGIS renderer style (depths, buoys, lights,
   fairway, anchor areas, harbours, moles, obstacles, bridges, locks, shore).

## Configuration

Edit the constants at the top of `build_vltava_labe.py` directly
(`config_example.txt` is not read by the script — a vestige of an older
version):

- `INPUT_DIR` / `OUTPUT_DIR` — resolved relative to the script's own location
- `MIN_ZOOM = 10`, `MAX_ZOOM = 16` — 16 is deliberate; raising to 17–18
  dramatically increases tile count and render time

## OsmAnd settings

- `ellipsoid = 0`
- `inverted_y = 0`
- `tilenumbering = ''` (normal spherical Web Mercator XYZ)
- `tilesize = 256`

## Troubleshooting

If the script fails with a GDAL/S-57 error, check
`output/S57_layers_report.txt` — it lists the layers GDAL actually sees in
each `*.000` cell.

## License

Code is licensed under the [MIT License](LICENSE). The S-57/IENC chart data
remains subject to the terms of its original providers.
