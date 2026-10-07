"""
MODFLOW CELL COORDINATE GENERATOR — ALL CELLS
Written By: Ankush Kaundal
Reads: config.yaml  ->  section: cell_coordinates
Produces ONE CSV:
  <model_name>_all_cells_coordinates.csv
  Columns: Cell_ID, Layer, Row, Column, Easting, Northing
"""

import sys
import os

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import pandas as pd
from config_loader import load_config, output_path, cell_centroid


# LOAD CONFIG
cfg        = load_config("config.yaml")
MODEL      = cfg["model_name"]
section    = cfg["cell_coordinates"]

if not section["run"]:
    print("cell_coordinates: run = false — skipping.")
    sys.exit(0)

params     = section["parameters"]
output_dir = section["outputs"]["output_dir"]
OUT_CSV    = output_path(MODEL, output_dir, "all_cells_coordinates.csv")

NLAY = params["nlay"]
NROW = params["nrow"]
NCOL = params["ncol"]

print("=" * 60)
print("CELL COORDINATE GENERATOR — ALL CELLS")
print("=" * 60)
print(f"  Model         : {MODEL}")
print(f"  Grid          : {NLAY} layers x {NROW} rows x {NCOL} cols")
print(f"  Cell size     : {params['cell_size']} m")
print(f"  Origin corner : {params['origin_corner']}")
print(f"  Origin (E, N) : {params['origin_easting']:,}  {params['origin_northing']:,}")
print(f"  Total cells   : {NLAY * NROW * NCOL:,}")
print(f"  Output        : {OUT_CSV}")


# BUILD TABLE
print("\nComputing centroids ...")
rows_all = []
for lay in range(1, NLAY + 1):
    for row in range(1, NROW + 1):
        for col in range(1, NCOL + 1):
            e, n = cell_centroid(row, col, params)
            rows_all.append({
                "cell_id" : f"L{lay}R{row}C{col}",
                "layer"   : lay,
                "row"     : row,
                "column"  : col,
                "easting" : e,
                "northing": n,
            })

df = pd.DataFrame(rows_all)
df.to_csv(OUT_CSV, index=False)
print(f"   Saved {len(df):,} rows -> {OUT_CSV}")

# Corner spot-checks
print(f"\n   Corner centroid checks:")
for label, r, c in [("Top-Left    ", 1,    1),
                     ("Top-Right   ", 1,    NCOL),
                     ("Bottom-Left ", NROW, 1),
                     ("Bottom-Right", NROW, NCOL)]:
    e, n = cell_centroid(r, c, params)
    print(f"     {label} (R{r:4d}, C{c:4d})  ->  E {e:,.0f}   N {n:,.0f}")

e_tl, n_tl = cell_centroid(1,    1,    params)
e_br, n_br = cell_centroid(NROW, NCOL, params)
print(f"\n   Grid extent:")
print(f"     Easting  : {min(e_tl,e_br):,.0f} -> {max(e_tl,e_br):,.0f}  "
      f"({NCOL * params['cell_size'] / 1000:.1f} km)")
print(f"     Northing : {min(n_tl,n_br):,.0f} -> {max(n_tl,n_br):,.0f}  "
      f"({NROW * params['cell_size'] / 1000:.1f} km)")

print(f"\n{'=' * 60}\nCOMPLETE\n{'=' * 60}")
