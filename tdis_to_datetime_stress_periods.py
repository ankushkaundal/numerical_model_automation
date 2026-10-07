"""
MODFLOW 6 TDIS File — Stress Period & Timestep Timing parser
Written By: Ankush Kaundal
Reads: config.yaml  ->  section: dis_timing
Produces ONE Excel file (plain, no colours):
  <model_name>_dis_timing.xlsx
  Sheet 1 "Summary"  — one row per stress period
  Sheet 2 "Detailed" — one row per timestep
"""

import sys
import os

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import re
import pandas as pd
from datetime import datetime, timedelta
from config_loader import load_config, output_path, get_start_date

# LOAD CONFIG
cfg     = load_config("config.yaml")
MODEL   = cfg["model_name"]
section = cfg["dis_timing"]

if not section["run"]:
    print("dis_timing: run = false — skipping.")
    sys.exit(0)

TDIS_FILE = section["inputs"]["dis_file"]   # reuse same key
output_dir = section["outputs"]["output_dir"]
START_DATE = get_start_date(section)
OUT_XLSX   = output_path(MODEL, output_dir, "tdis_timing.xlsx")

print("=" * 60)
print("MODFLOW 6 TDIS TIMING PARSER")
print("=" * 60)
print(f"  Model      : {MODEL}")
print(f"  TDIS file  : {TDIS_FILE}")
print(f"  Start date : {START_DATE.strftime('%d/%m/%Y')}")
print(f"  Output     : {OUT_XLSX}")


# STEP 1: READ TDIS HEADER (NPER + optional start date)
def read_tdis_header(tdis_file):
    nper = None
    start_dt = None

    in_dimensions = False
    in_options = False

    with open(tdis_file, encoding='latin-1') as fh:
        for line in fh:
            stripped = line.strip()

            if stripped.upper().startswith("BEGIN DIMENSIONS"):
                in_dimensions = True
                continue
            elif stripped.upper().startswith("END DIMENSIONS"):
                in_dimensions = False

            if stripped.upper().startswith("BEGIN OPTIONS"):
                in_options = True
                continue
            elif stripped.upper().startswith("END OPTIONS"):
                in_options = False

            if in_dimensions and "NPER" in stripped.upper():
                nper = int(stripped.split()[1])

            if in_options and "START_DATE_TIME" in stripped.upper():
                dt_str = stripped.split()[1]
                try:
                    start_dt = datetime.fromisoformat(dt_str)
                except Exception:
                    pass

    if nper is None:
        raise ValueError("Could not find NPER in TDIS file.")

    return {
        "NPER": nper,
        "START_DATE_TIME_FILE": start_dt
    }


# STEP 2: EXTRACT PERIODDATA
# Format:
#   perlen  nstp  tsmult   # optional comment
def parse_tdis_perioddata(tdis_file, nper):

    sp_pattern = re.compile(
        r'^\s*([\d.]+(?:[Ee][+-]?\d+)?)'   # PERLEN
        r'\s+(\d+)'                        # NSTP
        r'\s+([\d.]+(?:[Ee][+-]?\d+)?)'    # TSMULT
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
                records.append((
                    float(m.group(1)),
                    int(m.group(2)),
                    float(m.group(3)),
                    "TR"   # MF6 has no SS/TR flag → default transient
                ))

    if len(records) < nper:
        print(f"  WARNING: expected {nper}, found {len(records)}")

    return records


# STEP 3a: SUMMARY
def build_summary(sp_records, start_date):
    rows = []
    cum = 0.0

    for i, (perlen, nstp, tsmult, ss_tr) in enumerate(sp_records):
        rows.append({
            "stress_period": i + 1,
            "perlen_days": round(perlen, 4),
            "nstp": nstp,
            "tsmult": round(tsmult, 4),
            "ss_tr": ss_tr,
            "sp_start_date": (start_date + timedelta(days=cum)).strftime("%d/%m/%Y"),
            "sp_end_date": (start_date + timedelta(days=cum + perlen)).strftime("%d/%m/%Y"),
            "sp_start_day": round(cum, 4),
            "sp_end_day": round(cum + perlen, 4),
        })
        cum += perlen

    return pd.DataFrame(rows)


# STEP 3b: DETAILED
def build_detailed(sp_records, start_date):
    rows = []
    cum = 0.0

    for i, (perlen, nstp, tsmult, ss_tr) in enumerate(sp_records):
        kper_1 = i + 1
        sp_start_date = start_date + timedelta(days=cum)
        sp_end_date   = start_date + timedelta(days=cum + perlen)

        if abs(tsmult - 1.0) < 1e-9:
            dts = [perlen / nstp] * nstp
        else:
            dt1 = perlen * (tsmult - 1.0) / (tsmult ** nstp - 1.0)
            dts = [dt1 * tsmult ** j for j in range(nstp)]

        ts_elapsed = 0.0

        for j, dt in enumerate(dts):
            ts_start = cum + ts_elapsed
            ts_end   = ts_start + dt

            rows.append({
                "stress_period": kper_1,
                "timestep": j + 1,
                "perlen_days": round(perlen, 4),
                "nstp": nstp,
                "tsmult": round(tsmult, 4),
                "ss_tr": ss_tr,
                "sp_start_date": sp_start_date.strftime("%d/%m/%Y"),
                "sp_end_date": sp_end_date.strftime("%d/%m/%Y"),
                "sp_start_day": round(cum, 4),
                "sp_end_day": round(cum + perlen, 4),
                "ts_start_day": round(ts_start, 4),
                "ts_end_day": round(ts_end, 4),
                "ts_duration_day": round(dt, 6),
                "ts_start_date": (start_date + timedelta(days=ts_start)).strftime("%d/%m/%Y"),
                "ts_end_date": (start_date + timedelta(days=ts_end)).strftime("%d/%m/%Y"),
            })
            ts_elapsed += dt
        cum += perlen
    return pd.DataFrame(rows)


# MAIN
print("\nReading TDIS header ...")
header = read_tdis_header(TDIS_FILE)

for k, v in header.items():
    print(f"   {k:20s} = {v}")

print(f"\nExtracting {header['NPER']} stress period records ...")
sp_records = parse_tdis_perioddata(TDIS_FILE, header['NPER'])

print(f"   {len(sp_records)} stress periods read.")
print(f"   NSTP values  : {set(r[1] for r in sp_records)}")
print(f"   TSMULT values: {set(r[2] for r in sp_records)}")

print("\nBuilding Summary sheet ...")
df_summary = build_summary(sp_records, START_DATE)
print(f"   {len(df_summary):,} rows")

print("Building Detailed sheet ...")
df_detailed = build_detailed(sp_records, START_DATE)
print(f"   {len(df_detailed):,} rows")

total_days = df_summary["sp_end_day"].iloc[-1]
end_date   = df_summary["sp_end_date"].iloc[-1]

print(f"\n   {START_DATE.strftime('%d/%m/%Y')} -> {end_date}")
print(f"   Total : {total_days:,.1f} days  ({total_days/365.25:.2f} years)")

print("\nWriting Excel workbook ...")
ROW_LIMIT = 1_000_000

with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
    df_summary.to_excel(writer, sheet_name="summary", index=False)

    if len(df_detailed) <= ROW_LIMIT:
        df_detailed.to_excel(writer, sheet_name="detailed", index=False)
    else:
        parts = [df_detailed.iloc[i:i+ROW_LIMIT] for i in range(0, len(df_detailed), ROW_LIMIT)]
        for ridx, part in enumerate(parts, 1):
            sname = "detailed" if ridx == 1 else f"detailed_r{ridx}"
            part.to_excel(writer, sheet_name=sname, index=False)

print(f"\nSaved: {OUT_XLSX}")
print("=" * 60)