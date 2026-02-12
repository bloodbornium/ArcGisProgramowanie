import sys
import pandas as pd
from pathlib import Path
import arcpy
import shutil
from tqdm import tqdm
import numpy as np
from PIL import Image


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Projekt/dane"      
OUTPUT_DIR = BASE_DIR / "Projekt/wynik"     
OUTPUT_DIR.mkdir(exist_ok=True)


#czyszczenie katalogów temp
if "clear" in sys.argv:
    folder = Path("Projekt/wynik")
    for file in folder.iterdir():
        try:
            if file.is_dir():
                shutil.rmtree(file)
            else:
                file.unlink()
        except Exception as e:
            print(f"Błąd przy usuwaniu {file}: {e}")
    print("usunięto wszystko w folderze wynikowym")
    sys.exit(0)


#ustalenie nazwy pliku csv
CSV_OUTPUT_NAME = "bus_points.csv"
if "-oCsv" in sys.argv:
    csvOutputIndex = sys.argv.index("-oCsv") + 1
    CSV_OUTPUT_NAME = sys.argv[csvOutputIndex] + ".csv"
#ustalenie nazwy pliku shp
SHP_OUTPUT_NAME = "wynik.shp"
if "-oShp" in sys.argv:
    shpOutputIndex = sys.argv.index("-oShp") + 1
    SHP_OUTPUT_NAME = sys.argv[shpOutputIndex] + ".shp"
#ustalenie nazwy finalnej heatmapy
TIF_OUTPUT_NAME = "heatmap.tif"
if "-oTif" in sys.argv:
    tifOutputIndex = sys.argv.index("-oTif") + 1
    TIF_OUTPUT_NAME = sys.argv[csvOutputIndex] + ".tif"

CSV_FILE = OUTPUT_DIR / CSV_OUTPUT_NAME
WYNIK_SHP = OUTPUT_DIR / SHP_OUTPUT_NAME      
SHAPEFILE = WYNIK_SHP
OUTPUT_TIF = OUTPUT_DIR / TIF_OUTPUT_NAME
#max busy
MAX_BUS = 100000
if "-oMaxBus" in sys.argv:
    MAX_BUS = int(sys.argv[sys.argv.index("-oMaxBus") + 1])
                  

#decydowanie czy generować csv
genCsv = True
if "noCsv" in sys.argv:
    genCsv = False
#decydowanie czy generować shp
genShp = True
if "noShp" in sys.argv:
    genShp = False
genTif = True
if "noTif" in sys.argv:
    genTif = False
#rozdzielczość pikseli 
PIXELS = 500  # normalnie lepiej dać więcej, ale laguje przy dużych danych
if "-oPixel" in sys.argv:
    PIXELS = int(sys.argv[sys.argv.index("-oPixel") + 1])






if genCsv:
    STOP_TIMES_FILE = DATA_DIR / "stop_times.txt"
    STOPS_FILE = DATA_DIR / "stops.txt"
    
    stop_times = pd.read_csv(STOP_TIMES_FILE)
    stops = pd.read_csv(STOPS_FILE)
    
    df = stop_times.merge(
        stops[["stop_id", "stop_lat", "stop_lon"]],
        on="stop_id",
        how="left"
    )
    df = df.sort_values(["trip_id", "stop_sequence"])
    
    bus_map = {trip: i for i, trip in enumerate(df["trip_id"].unique())}
    df["bus_id"] = df["trip_id"].map(bus_map)
    
    df_out = df[["bus_id", "stop_sequence", "stop_lat", "stop_lon"]].rename(
        columns={"stop_lat": "lat", "stop_lon": "lon"}
    )
    df_out.to_csv(CSV_FILE, index=False)
else:
    if not CSV_FILE.exists():
        raise FileNotFoundError(f"Nie znaleziono CSV w {CSV_FILE}")
    df_out = pd.read_csv(CSV_FILE)

if genShp:
    bus_ids_all = sorted(df_out["bus_id"].unique())
    bus_ids = bus_ids_all[:MAX_BUS]
    print(f"ℹ Liczba autobusów do przetworzenia: {len(bus_ids)}")


    if arcpy.Exists(str(WYNIK_SHP)):
        arcpy.management.Delete(str(WYNIK_SHP))

    spatial_ref = arcpy.SpatialReference(2180)

    arcpy.management.CreateFeatureclass(
        out_path=str(OUTPUT_DIR),
        out_name=WYNIK_SHP.name,
        geometry_type="POLYLINE",
        spatial_reference=spatial_ref
    )

    arcpy.management.AddField(str(WYNIK_SHP), "bus_id", "LONG")

    print("Tworzenie linii autobusów w shapefile wynik.shp...")

    with arcpy.da.InsertCursor(str(WYNIK_SHP), ["bus_id", "SHAPE@"]) as cursor:
        for idx, bus_id in enumerate(bus_ids, start=1):
            df_bus = df_out[df_out["bus_id"] == bus_id].sort_values("stop_sequence")
            points = [arcpy.Point(xy[0], xy[1]) for xy in zip(df_bus["lon"], df_bus["lat"])]
            if not points:
                continue
            array = arcpy.Array(points)
            polyline = arcpy.Polyline(array, spatial_ref)
            cursor.insertRow([bus_id, polyline])

            if idx % 10 == 0 or idx == len(bus_ids):
                print(f"Zrobione {idx}/{len(bus_ids)} autobusów")

    print("Shapefile wynik.shp został utworzony w:", WYNIK_SHP)



##### CZĘŚĆ RASTROWA ######
if genTif:
    
    x_list = []
    y_list = []

    print("Pobieranie punktów z linii...")

    with arcpy.da.SearchCursor(str(SHAPEFILE), ["SHAPE@"]) as cursor:
        for row in tqdm(cursor):
            polyline = row[0]
            if polyline is None:
                continue 
            for part in polyline:
                if part is None:
                    continue
                for point in part:
                    if point is not None:
                        x_list.append(point.X)
                        y_list.append(point.Y)

    if not x_list or not y_list:
        raise ValueError("Brak punktów w shapefile!")

    x_min, x_max = min(x_list), max(x_list)
    y_min, y_max = min(y_list), max(y_list)

    cols = PIXELS
    rows = PIXELS

    cell_size_x = (x_max - x_min) / cols
    cell_size_y = (y_max - y_min) / rows

    heatmap = np.zeros((rows, cols), dtype=np.float32)

    def coord_to_index(x, y):
        col = int((x - x_min) / cell_size_x)
        row = int((y_max - y) / cell_size_y) 
        col = np.clip(col, 0, cols - 1)
        row = np.clip(row, 0, rows - 1)
        return row, col

    print("Rasterowanie linii...")

    with arcpy.da.SearchCursor(str(SHAPEFILE), ["SHAPE@"]) as cursor:
        for row in tqdm(cursor):
            polyline = row[0]
            if polyline is None:
                continue
            for part in polyline:
                if part is None:
                    continue
                pts = [p for p in part if p is not None]
                for i in range(len(pts)-1):
                    x0, y0 = pts[i].X, pts[i].Y
                    x1, y1 = pts[i+1].X, pts[i+1].Y

                    n = max(abs(x1 - x0)/cell_size_x, abs(y1 - y0)/cell_size_y, 1)
                    for t in np.linspace(0, 1, int(n)+1):
                        x = x0 + t*(x1 - x0)
                        y = y0 + t*(y1 - y0)
                        r, c = coord_to_index(x, y)
                        heatmap[r, c] += 1

    print("Robienie heatmapy...")

    heatmap_log = np.log1p(heatmap)  
    heatmap_norm = (heatmap_log / heatmap_log.max() * 255).astype(np.uint8)

    r = heatmap_norm
    g = 255 - heatmap_norm
    b = 255 - heatmap_norm

    rgb = np.stack([r, g, b], axis=2)
    img = Image.fromarray(rgb)
    img.save(OUTPUT_TIF)

    print("Heatmapa zapisana jako:", OUTPUT_TIF)