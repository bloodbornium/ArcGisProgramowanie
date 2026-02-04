import pandas as pd
from pathlib import Path
import arcpy


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Projekt/dane"      
OUTPUT_DIR = BASE_DIR / "Projekt/wynik"     
OUTPUT_DIR.mkdir(exist_ok=True)

CSV_FILE = OUTPUT_DIR / "bus_points.csv"
WYNIK_SHP = OUTPUT_DIR / "wynik.shp"        
MAX_BUS = 100000                             
genCsv = True


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
