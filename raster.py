import arcpy
import numpy as np
from pathlib import Path
from tqdm import tqdm
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
SHAPEFILE = BASE_DIR / "Projekt/wynik/wynik.shp"
OUTPUT_TIF = BASE_DIR / "Projekt/wynik/heatmap.tif"

PIXELS = 500  # normalnie lepiej dać więcej, ale laguje przy dużych danych

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

print("🗺️ Rasterowanie linii...")

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
