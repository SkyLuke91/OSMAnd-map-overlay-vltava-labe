# Vltava + Labe → OsmAnd (S-57/IENC raster overlay)

Skript `build_vltava_labe.py` převádí české vnitrozemské S-57/IENC mapové buňky
(řeky Vltava a Labe, soubory jako `9D7VL047.000`, `9D7EL726.000`) na
průhledný rastrový overlay pro [OsmAnd](https://osmand.net/) — SQLite tile
databázi (`Vltava_Labe.sqlitedb`).

> ⚠️ Výstup je vizualizační overlay. Nenahrazuje Inland ECDIS a neměl by být
> používán jako jediný navigační prostředek.

[English version](README.md)

## Požadavky

- QGIS s podporou PyQGIS, Qt a GDAL S-57 driveru (testováno na Windows).
- Skript **běží jen v QGIS Python Console** — samostatné Python/GDAL na tomto
  stroji chybí.

## Instalace

```bash
git clone https://github.com/SkyLuke91/mapy_vltava_labe.git
```

## Použití

1. V QGIS otevřete **Plugins → Python Console**.
2. Spusťte:

```python
exec(open(r"C:\cesta\k\mapy_vltava_labe\build_vltava_labe.py", encoding="utf-8").read())
```

Výstup najdete v `output/`:

- `Vltava_Labe.sqlitedb` — OsmAnd tile databáze
- `Vltava_Labe_review.qgz` — QGIS projekt s načtenými S-57 vrstvami pro kontrolu
- `S57_layers_report.txt` — seznam vrstev, které GDAL v každé buňce skutečně vidí

V OsmAnd pak soubor přidejte jako **rastrovou overlay mapu**
(Mapy → Překryvová mapa / Overlay map).

## Struktura

```
build_vltava_labe.py     # hlavní (jediný) skript
input/                   # S-57 buňky *.000 (glob je nerekurzivní)
input/later/             # archiv dalších buněk — build je IGNORUJE
output/                  # výstup sqlitedb + qgz + report
source of maps/          # původní zdrojové archivy (*.zip)
```

## Jak to funguje

1. `find_s57_cells()` najde `input/*.000` a zapíše layer report.
2. Načte se přes OGR provider s `UPDATES=APPLY`, `SPLIT_MULTIPOINT=ON`,
   `ADD_SOUNDG_DEPTH=ON` (bod SOUNDG dostane atribut `DEPTH`).
3. Načtené vrstvy: DEPCNT, SOUNDG, bóje, majáky (BOY*/BCN*), LIGHTS, FAIRWY,
   ACHARE, HRBPRT, MORFAC, OBSTRN, WRECKS, BRIDGE, GATCON, SLCONS, DAMCON,
   COALNE a další. Chybějící vrstvy se přeskočí, nejsou chybou.
4. Pro každý zoom 10–16 se vyrenderují průhledné 256px PNG dlaždice;
   prázdné (`is_blank()`) se přeskočí, zbytek jde do SQLite.
5. Každá vrstva dostane jednoduchý QGIS styl (hloubky, bóje, majáky, fairway…).

## Konfigurace

Konstanty upravte přímo na začátku `build_vltava_labe.py`
(`config_example.txt` skript nečte — pozůstatek starší verze):

- `INPUT_DIR` / `OUTPUT_DIR` — relativní k umístění skriptu
- `MIN_ZOOM = 10`, `MAX_ZOOM = 16` — 16 je záměrné; 17–18 dramaticky zvětší
  počet dlaždic a dobu renderování

## OsmAnd parametry

- `ellipsoid = 0`
- `inverted_y = 0`
- `tilenumbering = ''` (normální sférický Web Mercator XYZ)
- `tilesize = 256`

## Řešení problémů

Skončí-li skript na GDAL/S-57 chybě, zkontrolujte `output/S57_layers_report.txt` —
ukazuje vrstvy, které GDAL v jednotlivých `*.000` buňkách skutečně vidí.

## Licence

Kód je licencován pod [MIT](LICENSE). Mapová data S-57/IENC podléhají
podmínkám jejich původních poskytovatelů.
