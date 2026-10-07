
'''Modflow 6 utility produced stream flow/leakage files are used directly to make them to be used for fdc analysis
Written By: Ankush Kaundal
Reads: config.yaml  ->  section: cs2_analysis
No .cs1/cbc file involved —
the MF6 SFR utility already produces per-cell leakage/flowout CSVs with
columns named L#R#C# and a "time" column (cumulative days).
Timing derived from TDIS file (MODFLOW 6).
All paths and parameters come from config.yaml'''

## uodated the script to convert negative MF6 flowout (sfr_allcells_totalflow.csv) outputs to +ve flow values for FDC tool

import sys
import os

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import re
import pandas as pd
from datetime import timedelta
from config_loader import load_config, output_path, get_start_date, cell_centroid


# LOAD CONFIG
cfg     = load_config("config.yaml")
MODEL   = cfg["model_name"]
section = cfg["cs2_analysis"]

if not section["run"]:
    print("cs2_analysis: run = false — skipping.")
    sys.exit(0)

LEAKAGE_CSV = section["inputs"]["leakage_csv"]
FLOWOUT_CSV = section["inputs"]["flowout_csv"]
TDIS_FILE   = section["inputs"]["dis_file"]
output_dir  = section["outputs"]["output_dir"]
params      = section["parameters"]
PARTS       = section["parts"]
START_DATE  = get_start_date(section)

def out(filename):
    return output_path(MODEL, output_dir, filename)

print("=" * 60)
print("CS2 ANALYSIS — MODFLOW 6 SFR UTILITY CSVs")
print("=" * 60)
print(f"  Model       : {MODEL}")
print(f"  Leakage CSV : {LEAKAGE_CSV}")
print(f"  Flowout CSV : {FLOWOUT_CSV}")
print(f"  TDIS file   : {TDIS_FILE}")
print(f"  Start       : {START_DATE.strftime('%d/%m/%Y')}")
print(f"\n  Parts enabled:")
for k, v in PARTS.items():
    print(f"    {k:<22s} : {'YES' if v else 'skip'}")
print("=" * 60)



# PARSE TDIS FILE FOR STRESS PERIOD TIMING

def read_tdis_header(tdis_file):
    nper = None
    in_dimensions = False
    with open(tdis_file, encoding='latin-1') as fh:
        for line in fh:
            stripped = line.strip()
            if stripped.upper().startswith("BEGIN DIMENSIONS"):
                in_dimensions = True
                continue
            elif stripped.upper().startswith("END DIMENSIONS"):
                in_dimensions = False
            if in_dimensions and "NPER" in stripped.upper():
                nper = int(stripped.split()[1])
    if nper is None:
        raise ValueError("Could not find NPER in TDIS file.")
    return nper


def parse_tdis_perioddata(tdis_file, nper):
    sp_pattern = re.compile(
        r'^\s*([\d.]+(?:[Ee][+-]?\d+)?)'
        r'\s+(\d+)'
        r'\s+([\d.]+(?:[Ee][+-]?\d+)?)'
    )
    records = []
    in_perioddata = False
    with open(tdis_file, encoding='latin-1') as fh:
        for line in fh:
            stripped = line.strip()
            if stripped.upper().startswith("BEGIN PERIODDATA"):
                in_perioddata = True
                continue
            elif stripped.upper().startswith("END PERIODDATA"):
                break
            if not in_perioddata or stripped.startswith("#") or stripped == "":
                continue
            m = sp_pattern.match(stripped)
            if m:
                records.append((float(m.group(1)), int(m.group(2)), float(m.group(3))))
    if len(records) < nper:
        print(f"  WARNING: expected {nper}, found {len(records)}")
    return records


def build_sp_summary(sp_records, start_date):
    """One row per stress period: sp_end_days, stress_period, nstp, sp_end_date."""
    rows = []
    cum = 0.0
    for i, (perlen, nstp, tsmult) in enumerate(sp_records):
        cum += perlen
        rows.append({
            "stress_period": i + 1,
            "nstp": nstp,
            "sp_end_day": round(cum, 2),
            "sp_end_date": (start_date + timedelta(days=cum)).strftime("%d/%m/%Y"),
        })
    return pd.DataFrame(rows)


print("\nParsing TDIS file for timing ...")
nper       = read_tdis_header(TDIS_FILE)
sp_records = parse_tdis_perioddata(TDIS_FILE, nper)
df_time    = build_sp_summary(sp_records, START_DATE)
print(f"   {len(df_time):,} stress periods read.")



# HELPER: PARSE L#R#C# COLUMN HEADERS
CELL_PATTERN = re.compile(r'^L(\d+)R(\d+)C(\d+)$')

def get_cell_columns(df):
    return [c for c in df.columns if CELL_PATTERN.match(c.strip())]


# PART: ACTIVE CELLS WITH BNG COORDINATES (from column headers)
def build_active_cells_csv(csv_path, label):
    df = pd.read_csv(csv_path)
    cell_cols = get_cell_columns(df)
    rows = []
    for col in cell_cols:
        m = CELL_PATTERN.match(col.strip())
        lay, row, col_no = int(m.group(1)), int(m.group(2)), int(m.group(3))
        e, n = cell_centroid(row, col_no, params)
        rows.append({
            "cell_id" : col.strip(),
            "layer"   : lay,
            "row"     : row,
            "column"  : col_no,
            "easting" : e,
            "northing": n,
        })
    df_out = pd.DataFrame(rows)

    # Sort numerically by layer, row, and column
    df_out = (
        df_out
        .sort_values(["layer", "row", "column"])
        .reset_index(drop=True)
    )

    fp = out(f"{label}_active_cells_coordinates.csv")
    df_out.to_csv(fp, index=False)
    print(f"   {label}: {len(df_out):,} cells -> {fp}")


if PARTS.get("active_cells", True):
    print("\n" + "=" * 60)
    print("PART — ACTIVE CELLS WITH COORDINATES")
    print("=" * 60)
    build_active_cells_csv(LEAKAGE_CSV, "leakage")
    build_active_cells_csv(FLOWOUT_CSV, "flowout")
else:
    print("\nACTIVE CELLS part skipped")



# PART: TIMESERIES CSV MERGED WITH TDIS TIMING

def build_timeseries_csv(csv_path, label):
    df = pd.read_csv(csv_path)
    df_ren = df.rename(columns=lambda x: x.strip())
    df_ren["time"] = df_ren["time"].astype(float).round(2)

    #### flowout (in negative values)  from MF6 cauvery converted to postive values for fdc tools
    if label.lower() == "flowout":
        value_cols = df_ren.columns.difference(["time"])
        df_ren[value_cols] = -df_ren[value_cols]

    df_merged = pd.merge(
        df_ren,
        df_time,
        left_on="time",
        right_on="sp_end_day",
        how="inner"
    )
    # print(df_merged.columns.tolist())

    df_merged["timestep"] = df_merged["nstp"]
    cell_cols = get_cell_columns(df)

    df_final = df_merged.rename(columns={
        "stress_period": "stress_period",
        "sp_end_date"  : "sp_end_date",
    })[
        ["stress_period", "timestep", "sp_end_date"] + cell_cols
    ].sort_values("stress_period")

    fp = out(f"{label}_timeseries.csv")
    df_final.to_csv(fp, index=False)
    print(f"   {label}: {len(df_final):,} rows -> {fp}")


if PARTS.get("timeseries", True):
    print("\n" + "=" * 60)
    print("PART — TIMESERIES CSV WITH DATES")
    print("=" * 60)
    build_timeseries_csv(LEAKAGE_CSV, "leakage")
    build_timeseries_csv(FLOWOUT_CSV, "flowout")
else:
    print("\nTIMESERIES part skipped")

print("\n" + "=" * 60)
print("CS2 ANALYSIS COMPLETE")
print("=" * 60)
