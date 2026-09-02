# -*- coding: utf-8 -*-
"""
Vltava_Labe_OsmAnd - corrected S-57/IENC -> OsmAnd SQLite overlay

Spouštěj V QGIS Python Console:
    exec(open(r"C:\...\build_vltava_labe.py", encoding="utf-8").read())

Adresářová struktura:
    build_vltava_labe.py
    Vltava_Labe_OsmAnd/
        input/
            *.000
            případně *.001, *.002, ...
        output/

Skript:
  1) automaticky používá adresář, kde leží tento .py soubor
  2) načte S-57 přes GDAL/OGR
  3) zapne SPLIT_MULTIPOINT + ADD_SOUNDG_DEPTH
  4) automaticky zjistí dostupné S-57 vrstvy
  5) vytvoří transparentní navigační overlay
  6) zapíše přímo OsmAnd SQLite tile DB (.sqlitedb)
  7) vytvoří QGIS projekt s načtenými S-57 vrstvami pro kontrolu

Poznámka:
  - Výchozí zoom je 10–16, aby databáze nebyla zbytečně obrovská.
  - Pro detailnější výstup změň MAX_ZOOM na 17 nebo 18, ale počet dlaždic
    může výrazně narůst.
  - Výstup je vizualizační overlay, nikoli náhrada Inland ECDIS.
"""

from pathlib import Path
import os
import sys
import math
import sqlite3
import traceback
from datetime import datetime

print("[VLTAVA-LABE] Spouštím build_vltava_labe.py...")

# ----------------------------------------------------------------------
# PATHS - automaticky podle umístění tohoto skriptu
# ----------------------------------------------------------------------
try:
    SCRIPT_DIR = Path(__file__).resolve().parent
except NameError:
    # exec() v QGIS Python Console nemá __file__ — použij aktuální adresář
    SCRIPT_DIR = Path.cwd()
BASE_DIR = SCRIPT_DIR
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_SQLITE = OUTPUT_DIR / "Vltava_Labe.sqlitedb"
OUT_QGZ = OUTPUT_DIR / "Vltava_Labe_review.qgz"
OUT_REPORT = OUTPUT_DIR / "S57_layers_report.txt"

MIN_ZOOM = 10
MAX_ZOOM = 16
TILE_SIZE = 256

# ----------------------------------------------------------------------
# S-57 GDAL options
# ----------------------------------------------------------------------
os.environ["OGR_S57_OPTIONS"] = (
    "UPDATES=APPLY,"
    "SPLIT_MULTIPOINT=ON,"
    "ADD_SOUNDG_DEPTH=ON"
)

try:
    from osgeo import ogr, gdal
except Exception:
    raise RuntimeError(
        "V tomto QGIS Python prostředí není dostupný osgeo/GDAL. "
        "Spusť skript v QGIS Python Console, ne v běžném Pythonu."
    )

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsRectangle,
    QgsMapSettings,
    QgsMapRendererParallelJob,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsSymbol,
    QgsSingleSymbolRenderer,
    QgsLineSymbol,
    QgsFillSymbol,
    QgsMarkerSymbol,
    QgsSimpleMarkerSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsProperty,
    QgsUnitTypes,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter, QFont


# ----------------------------------------------------------------------
# Utility
# ----------------------------------------------------------------------
def log(msg):
    print("[VLTAVA-LABE] " + str(msg))
    sys.stdout.flush()  # Okamžité zobrazení v QGIS Console


def die(msg):
    log("CHYBA: " + msg)
    raise RuntimeError(msg)


def find_s57_cells():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    cells = sorted(INPUT_DIR.glob("*.000"))
    if not cells:
        die(
            "V INPUT_DIR nebyl nalezen žádný *.000 soubor:\n"
            f"  {INPUT_DIR}\n\n"
            "Očekávám například:\n"
            f"  {INPUT_DIR}\\9D7VL047.000"
        )
    return cells


def ogr_layers(path):
    ds = ogr.Open(str(path), 0)
    if ds is None:
        raise RuntimeError(f"GDAL nedokázal otevřít S-57: {path}")
    names = []
    for i in range(ds.GetLayerCount()):
        lyr = ds.GetLayer(i)
        names.append(lyr.GetName())
    ds = None
    return names


def write_layer_report(cells):
    lines = []
    for cell in cells:
        lines.append(f"\n=== {cell.name} ===")
        try:
            names = ogr_layers(cell)
            lines.extend("  " + n for n in names)
        except Exception as e:
            lines.append("  ERROR: " + repr(e))
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    log(f"Seznam S-57 vrstev: {OUT_REPORT}")


# ----------------------------------------------------------------------
# S-57 layers we want to show
# ----------------------------------------------------------------------
# Names are standard S-57 object class acronyms. Script only loads layers
# that actually exist in the supplied ENC cells.
LAYER_GROUPS = {
    "depth": ["DEPCNT", "SOUNDG"],
    "buoys": ["BOYLAT", "BOYCAR", "BOYSAW", "BOYISD", "BOYSPP"],
    "beacons": ["BCNISD", "BCNLAT", "BCNCAR", "BCNSAW", "BCNSPP", "DAYMAR"],
    "lights": ["LIGHTS"],
    "fairway": ["FAIRWY"],
    "anchor": ["ACHARE"],
    "harbour": ["HRBPRT", "HRBARE"],
    "moles": ["MORFAC"],
    "obstacles": ["OBSTRN", "WRECKS"],
    "bridges": ["BRIDGE"],
    "locks": ["GATCON", "SLCONS", "DAMCON"],
    "shore": ["COALNE", "LNDELV"],
}

ALL_WANTED = [x for group in LAYER_GROUPS.values() for x in group]


def load_qgis_layer(cell, layer_name):
    # QGIS/GDAL OGR URI for a named sublayer.
    uri = f"{cell}|layername={layer_name}"
    layer = QgsVectorLayer(uri, f"{cell.stem}_{layer_name}", "ogr")
    if not layer.isValid():
        # fallback URI form used by some QGIS builds
        uri2 = f"{cell}|layername={layer_name}"
        layer = QgsVectorLayer(uri2, f"{cell.stem}_{layer_name}", "ogr")
    if not layer.isValid():
        return None
    return layer


def field_names(layer):
    return {f.name().upper() for f in layer.fields()}


def value(feature, *names, default=None):
    for name in names:
        try:
            if name in feature.fields().names():
                v = feature[name]
                if v is not None and str(v) != "":
                    return v
        except Exception:
            pass
    return default


# ----------------------------------------------------------------------
# Styling
# ----------------------------------------------------------------------
def set_simple_line(layer, width=0.6, alpha=220, dashed=False):
    sym = QgsLineSymbol.createSimple({
        "color": QColor(0, 90, 190, alpha),
        "width": str(width),
    })
    if dashed:
        sl = sym.symbolLayer(0)
        if sl:
            sl.setCustomDashVector([3.0, 2.0])
    layer.setRenderer(QgsSingleSymbolRenderer(sym))


def set_simple_fill(layer, fill_rgba, outline_rgba=(0, 90, 190, 180), width=0.4):
    sym = QgsFillSymbol.createSimple({
        "color": QColor(*fill_rgba),
        "outline_color": QColor(*outline_rgba),
        "outline_width": str(width),
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))


def set_simple_marker(layer, size=3.2, rgba=(0, 90, 190, 230), shape="circle"):
    sym = QgsMarkerSymbol.createSimple({
        "name": shape,
        "color": QColor(*rgba),
        "size": str(size),
        "outline_color": QColor(255, 255, 255, 220),
        "outline_width": "0.35",
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))


def style_layer(layer, lname):
    n = lname.upper()

    if n == "DEPCNT":
        set_simple_line(layer, 0.45, 210)

    elif n == "SOUNDG":
        set_simple_marker(layer, 1.7, (20, 100, 190, 220))
        # Depth labels. GDAL ADD_SOUNDG_DEPTH=ON should provide DEPTH.
        try:
            if "DEPTH" in field_names(layer):
                pal = QgsPalLayerSettings()
                pal.fieldName = "DEPTH"
                pal.enabled = True
                tf = QgsTextFormat()
                tf.setFont(QFont("Arial", 7))
                tf.setSize(7)
                tf.setColor(QColor(10, 70, 140, 230))
                pal.setFormat(tf)
                layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
                layer.setLabelsEnabled(True)
        except Exception as e:
            log(f"  SOUNDG labelování přeskočeno: {e}")

    elif n in ("BOYLAT", "BOYCAR", "BOYSAW", "BOYISD", "BOYSPP"):
        set_simple_marker(layer, 3.4, (220, 40, 40, 235), "circle")

    elif n in ("BCNISD", "BCNLAT", "BCNCAR", "BCNSAW", "BCNSPP", "DAYMAR"):
        set_simple_marker(layer, 3.5, (240, 130, 20, 235), "triangle")

    elif n == "LIGHTS":
        set_simple_marker(layer, 3.0, (255, 230, 60, 240), "circle")

    elif n == "FAIRWY":
        set_simple_line(layer, 1.1, 200)

    elif n == "ACHARE":
        set_simple_fill(layer, (30, 120, 220, 35), (30, 100, 190, 170), 0.45)

    elif n in ("HRBPRT", "HRBARE"):
        set_simple_fill(layer, (30, 120, 220, 25), (30, 100, 190, 150), 0.45)

    elif n == "MORFAC":
        set_simple_line(layer, 1.0, 190)

    elif n in ("OBSTRN", "WRECKS"):
        set_simple_marker(layer, 3.0, (170, 30, 30, 230), "diamond")

    elif n == "BRIDGE":
        set_simple_line(layer, 1.4, 220)

    elif n in ("GATCON", "SLCONS", "DAMCON"):
        set_simple_line(layer, 1.4, 220)

    elif n == "COALNE":
        set_simple_line(layer, 0.8, 130)


# ----------------------------------------------------------------------
# Web Mercator tile helpers
# ----------------------------------------------------------------------
ORIGIN_SHIFT = 20037508.342789244
WEB_EXTENT = 2 * ORIGIN_SHIFT


def lonlat_to_tile(lon, lat, z):
    lat = max(-85.05112878, min(85.05112878, lat))
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int(
        (1.0 - math.asinh(math.tan(lat_rad)) / math.pi)
        / 2.0 * n
    )
    x = max(0, min(n - 1, x))
    y = max(0, min(n - 1, y))
    return x, y


def tile_extent_3857(x, y, z):
    n = 2 ** z
    size = WEB_EXTENT / n
    xmin = -ORIGIN_SHIFT + x * size
    xmax = xmin + size
    ymax = ORIGIN_SHIFT - y * size
    ymin = ymax - size
    return QgsRectangle(xmin, ymin, xmax, ymax)


def qgs_extent_to_tile_range(extent4326, z):
    x1, y1 = lonlat_to_tile(extent4326.xMinimum(), extent4326.yMaximum(), z)
    x2, y2 = lonlat_to_tile(extent4326.xMaximum(), extent4326.yMinimum(), z)
    return min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)


# ----------------------------------------------------------------------
# SQLite output
# ----------------------------------------------------------------------
def init_osmand_db(path):
    if path.exists():
        path.unlink()

    con = sqlite3.connect(str(path))
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE info (
            url TEXT,
            randoms TEXT,
            referer TEXT,
            rule TEXT,
            useragent TEXT,
            minzoom INTEGER,
            maxzoom INTEGER,
            ellipsoid INTEGER,
            inverted_y INTEGER,
            timecolumn TEXT,
            expireminutes INTEGER,
            tilenumbering TEXT,
            tilesize INTEGER
        )
    """)

    # IMPORTANT:
    # OsmAnd docs: normal spherical Web Mercator has ellipsoid=0;
    # normal XYZ tile numbering is represented by empty tilenumbering.
    cur.execute("""
        INSERT INTO info VALUES
        (?, '', '', '', '', ?, ?, 0, 0, 'no', 0, '', ?)
    """, (
        "local://Vltava_Labe/{z}/{x}/{y}.png",
        MIN_ZOOM,
        MAX_ZOOM,
        TILE_SIZE,
    ))

    cur.execute("""
        CREATE TABLE tiles (
            x INTEGER,
            y INTEGER,
            z INTEGER,
            image BLOB
        )
    """)

    cur.execute("CREATE INDEX idx_tiles_xyz ON tiles(x, y, z)")
    con.commit()
    return con


def image_to_png_bytes(img):
    from qgis.PyQt.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return data


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------
def render_tile(layers, x, y, z):
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    settings.setExtent(tile_extent_3857(x, y, z))
    settings.setOutputSize(QSize(TILE_SIZE, TILE_SIZE))
    settings.setOutputImageFormat(QImage.Format_ARGB32)
    settings.setBackgroundColor(QColor(255, 255, 255, 0))
    settings.setFlag(QgsMapSettings.Antialiasing, True)

    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    img = job.renderedImage()
    return img


def is_blank(img):
    # Fast-ish alpha test: if every pixel is fully transparent.
    # Sampling is enough to avoid storing empty tiles.
    w, h = img.width(), img.height()
    for yy in range(0, h, 16):
        for xx in range(0, w, 16):
            if QColor.fromRgba(img.pixel(xx, yy)).alpha() > 0:
                return False
    return True


def transform_project_extent_to_4326(layers):
    crs4326 = QgsCoordinateReferenceSystem("EPSG:4326")
    crs3857 = QgsCoordinateReferenceSystem("EPSG:3857")
    tr = QgsCoordinateTransform(crs3857, crs4326, QgsProject.instance())

    total = None
    for layer in layers:
        if not layer.isValid():
            continue
        e = layer.extent()
        if e.isEmpty():
            continue
        try:
            e4326 = tr.transformBoundingBox(e)
        except Exception:
            continue
        if total is None:
            total = QgsRectangle(e4326)
        else:
            total.combineExtentWith(e4326)
    return total


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def run():
    log(f"Script: {Path(__file__).resolve()}")
    log(f"INPUT_DIR:  {INPUT_DIR}")
    log(f"OUTPUT_DIR: {OUTPUT_DIR}")

    cells = find_s57_cells()
    log(f"Nalezeno S-57 buněk: {len(cells)}")
    write_layer_report(cells)

    project = QgsProject.instance()
    project.clear()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

    loaded = []
    seen = set()

    # Discover available layer names first.
    available = {}
    for cell in cells:
        names = set(ogr_layers(cell))
        available[cell] = names

    # Load only requested layers which actually exist.
    for cell in cells:
        for lname in ALL_WANTED:
            if lname not in available[cell]:
                continue

            key = (str(cell), lname)
            if key in seen:
                continue
            seen.add(key)

            log(f"Načítám {cell.name} / {lname}")
            layer = load_qgis_layer(cell, lname)
            if layer is None:
                log(f"  WARNING: QGIS layer se nepodařilo načíst: {lname}")
                continue

            style_layer(layer, lname)
            project.addMapLayer(layer, addToLegend=True)
            loaded.append(layer)

    if not loaded:
        die(
            "Z nalezených S-57 buněk se nepodařilo načíst žádnou "
            "z požadovaných navigačních vrstev. Podívej se do:\n"
            f"{OUT_REPORT}"
        )

    log("Načtené vrstvy:")
    for l in loaded:
        log("  " + l.name())

    # Save a review project so user can inspect the actual S-57 content.
    project.write(str(OUT_QGZ))
    log(f"Kontrolní QGIS projekt: {OUT_QGZ}")

    extent4326 = transform_project_extent_to_4326(loaded)
    if extent4326 is None or extent4326.isEmpty():
        die("Nepodařilo se určit geografický rozsah načtených vrstev.")

    log(
        "Rozsah WGS84: "
        f"{extent4326.xMinimum():.6f}, {extent4326.yMinimum():.6f} -> "
        f"{extent4326.xMaximum():.6f}, {extent4326.yMaximum():.6f}"
    )

    con = init_osmand_db(OUT_SQLITE)
    cur = con.cursor()

    inserted = 0
    rendered = 0

    try:
        for z in range(MIN_ZOOM, MAX_ZOOM + 1):
            xmin, xmax, ymin, ymax = qgs_extent_to_tile_range(extent4326, z)
            count = (xmax - xmin + 1) * (ymax - ymin + 1)
            log(f"Zoom {z}: kandidátních dlaždic {count}")

            for x in range(xmin, xmax + 1):
                for y in range(ymin, ymax + 1):
                    img = render_tile(loaded, x, y, z)
                    rendered += 1

                    if is_blank(img):
                        continue

                    blob = image_to_png_bytes(img)
                    cur.execute(
                        "INSERT INTO tiles(x,y,z,image) VALUES(?,?,?,?)",
                        (x, y, z, sqlite3.Binary(blob)),
                    )
                    inserted += 1

                # Commit průběžně, aby dlouhý běh nepřišel o všechno.
                if (x - xmin) % 8 == 0:
                    con.commit()
                    log(f"  z={z}: x={x}/{xmax}, uloženo {inserted}")

            con.commit()

    finally:
        con.close()

    log(f"Hotovo. Renderováno: {rendered}, uloženo: {inserted}")
    log(f"OsmAnd SQLite: {OUT_SQLITE}")
    log("V OsmAndu přidej soubor jako rastrový Overlay.")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
        raise
