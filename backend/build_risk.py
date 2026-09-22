import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.core.risk_h3 import build_static_cells, save_grid, GRID_PATH

if __name__ == "__main__":
    print(f"datum {settings.DATUM_LAT},{settings.DATUM_LON}")
    cells = build_static_cells(settings.DATUM_LAT, settings.DATUM_LON)
    save_grid(cells)
    print(f"saved {len(cells)} cells -> {GRID_PATH}")
