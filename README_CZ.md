# Vltava_Labe_OsmAnd – corrected

Tato verze je určena pro spuštění v QGIS Python Console.

## Umístění

Doporučená struktura:

C:\Users\Lukas\Downloads\mapy_vltava_labe\
├── build_vltava_labe.py
└── Vltava_Labe_OsmAnd\
    ├── input\
    │   ├── 9D7VL047.000
    │   └── další *.000 / případné *.001, *.002...
    └── output\

Skript už nepoužívá Path.home(). Cesty určuje relativně k umístění samotného
build_vltava_labe.py.

## Spuštění

V QGIS:
1. Plugins -> Python Console
2. spusť:

exec(open(r"C:\Users\Lukas\Downloads\mapy_vltava_labe\build_vltava_labe.py", encoding="utf-8").read())

Výstup bude v:

C:\Users\Lukas\Downloads\mapy_vltava_labe\Vltava_Labe_OsmAnd\output\

- Vltava_Labe.sqlitedb
- Vltava_Labe_review.qgz
- S57_layers_report.txt

## Co skript dělá

Používá GDAL S-57 driver a nastavuje:
- UPDATES=APPLY
- SPLIT_MULTIPOINT=ON
- ADD_SOUNDG_DEPTH=ON

Tím získá jednotlivé hloubkové body SOUNDG s atributem DEPTH, pokud je
příslušná informace v ENC datech.

Načítá dostupné vrstvy:
DEPCNT, SOUNDG, BOYLAT, BOYCAR, BOYSAW, BOYISD, BOYSPP,
BCNISD, BCNLAT, BCNCAR, BCNSAW, BCNSPP, DAYMAR, LIGHTS,
FAIRWY, ACHARE, HRBPRT, HRBARE, MORFAC, OBSTRN, WRECKS,
BRIDGE, GATCON, SLCONS, DAMCON, COALNE.

Pokud některá vrstva v konkrétní ENC buňce neexistuje, přeskočí ji.

## Důležité

Výchozí MAX_ZOOM = 16. To je záměrné. Zvyšování na 17 nebo 18 může
dramaticky zvětšit počet dlaždic a dobu renderování.

Výstupní SQLite používá normální OsmAnd tile numbering:
- ellipsoid = 0
- inverted_y = 0
- tilenumbering = ''
- tilesize = 256

## Pokud skript skončí na GDAL/S-57 chybě

Zkontroluj soubor:

output\S57_layers_report.txt

Ten ukáže vrstvy, které GDAL v jednotlivých *.000 buňkách skutečně vidí.

## Omezení

Výsledek je vizualizační rastrový overlay pro OsmAnd. Nenahrazuje Inland
ECDIS a neměl by být používán jako jediný navigační prostředek.
