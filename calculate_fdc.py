"""
Flow Duration curve Calculations
Written By: Ankush Kaundal
Reads: fdc_config.yaml

Produces:
  TWO Excel files (flowout and stream leakage), each with 4 sheets:
  Also produces Flow duration curves, plots maps of flow and leakage which quantiles and per_differences.
"""


### Functions safe_diff, safe_pct changed by Ankush on 29/09/2026 to get run1-run2, or baseline minus scenario differences
###  ###Changes made by ankush to GET SP timeseries in MLD by dividing m3/day by 1000 in build_comparision function.
### This way all outputs from FDC, SP timeseries, Quantilies will all be in Ml/Day, because we divide original m3/day by 1000 to get Ml/Day.

import os
import re
import sys
import yaml
import numpy as np
import pandas as pd
import textwrap
import matplotlib.pyplot as plt
import matplotlib as mpl

# PLOT FONT SETTINGS
TITLE_FONTSIZE      = 21
AXIS_LABEL_FONTSIZE = 21
TICK_LABEL_FONTSIZE = 19
LEGEND_FONTSIZE     = 19
LINE_WIDTH          = 6.8
FIGURE_SIZE         = (7.5, 5)
MAP_FIGURE_SIZE     = (12, 8)
MAP_POINT_SIZE      = 3.5

# LOAD AND RESOLVE CONFIG
def load_config(yaml_path="fdc_config.yaml"):
    if not os.path.isabs(yaml_path):
        yaml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), yaml_path)
    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return _resolve(cfg, cfg)


def _resolve(obj, cfg):
    model = cfg.get("model_name", "")
    run1  = cfg.get("run1_name",  "")
    run2  = cfg.get("run2_name",  "")
    root = cfg.get("model_root", "")
    def r(val):
        if isinstance(val, str):
            return (val.replace("{model_name}", model)
                       .replace("{run1_name}",  run1)
                       .replace("{run2_name}",  run2)
                       .replace("{model_root}", root))
        elif isinstance(val, dict):  return {k: r(v) for k, v in val.items()}
        elif isinstance(val, list):  return [r(v) for v in val]
        return val
    return {k: r(v) for k, v in obj.items()}


cfg         = load_config("fdc_config.yaml")
META        = cfg.get("metadata", {})
MODEL       = cfg["model_name"]
RUN1        = cfg["run1_name"]
RUN2        = cfg["run2_name"]
INPUTS      = cfg["inputs"]
OUTPUTS     = cfg["outputs"]
FILTER      = cfg["filter"]
SPS         = cfg["stress_periods"]
FDC_CFG     = cfg["fdc"]
PLOT_CFG    = cfg["plot"]
SHP_CFG     = cfg["shapefile"]
MAP_CFG     = cfg["map_plot"]
PERCENTILES = FDC_CFG["percentiles"]
FDC_SCALE   = FDC_CFG["scale"]
PCT_TYPE    = FDC_CFG.get("percentile_type", "type6")
PCT_METHOD  = "weibull" if PCT_TYPE == "type6" else "linear"

BASE_OUTPUT_DIR = OUTPUTS["output_dir"]
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
OUTPUT_DIR  = BASE_OUTPUT_DIR   # temporary, only used for the banner print below

# Build filename range string
if FILTER["filter_mode"] == "date_range":
    _sp1 = FILTER.get("date_start", "").replace("/", "")
    _sp2 = FILTER.get("date_end",   "").replace("/", "")
elif FILTER["filter_mode"] in ("sp_range", "sp_ts"):
    _sp1 = FILTER.get("sp_start", min(SPS))
    _sp2 = FILTER.get("sp_end",   max(SPS))
else:
    raise ValueError(f"Unknown filter_mode: {FILTER['filter_mode']}. Use: date_range | sp_range | sp_ts")
sp_range_str = f"sp{_sp1}_sp{_sp2}"
model_lower  = MODEL.lower()

# Build output filenames — all lowercase with SP range
OUT_FLOWOUT = os.path.join(OUTPUT_DIR,
    f"{model_lower}_{RUN1}_vs_{RUN2}_{sp_range_str}_fdc_flowout.xlsx")
OUT_LEAKAGE = os.path.join(OUTPUT_DIR,
    f"{model_lower}_{RUN1}_vs_{RUN2}_{sp_range_str}_fdc_leakage.xlsx")

print("=" * 60)
print("FDC ANALYSIS")
print(f"Executing script: {os.path.abspath(__file__)}")
print("=" * 60)
print(f"  Model            : {MODEL}  |  Run1 : {RUN1}  |  Run2 : {RUN2}")
print(f"  Filter           : {FILTER['filter_mode']}")
print(f"  SPs              : {SPS}  ({sp_range_str})")
print(f"  Percentile type  : {PCT_TYPE} ({PCT_METHOD})")
print(f"  Run analysis     : {FDC_CFG['run_analysis']}")
print(f"  Plot flowout     : {PLOT_CFG['plot_flowout']}")
print(f"  Plot leakage     : {PLOT_CFG['plot_leakage']}")
print(f"  Save flowout shp : {SHP_CFG['save_flowout_shapefile']}")
print(f"  Save leakage shp : {SHP_CFG['save_leakage_shapefile']}")
print(f"  Map flowout      : {MAP_CFG['plot_flowout_map']}")
print(f"  Map leakage      : {MAP_CFG['plot_leakage_map']}")
print(f"  Flowout xlsx     : {os.path.basename(OUT_FLOWOUT)}")
print(f"  Leakage xlsx     : {os.path.basename(OUT_LEAKAGE)}")


# HELPERS
def sort_cell_ids(cell_ids):
    """Sort cell IDs numerically by layer, row, col."""
    def key(cid):
        parts = cid.split("_")
        try: return (int(parts[1]), int(parts[2]), int(parts[3]))
        except: return (0, 0, 0)
    return sorted(cell_ids, key=key)

def collect_part_files(base_path):
    base, ext = os.path.splitext(base_path)
    files = [base_path] if os.path.exists(base_path) else []
    for f in sorted(os.listdir(os.path.dirname(base_path) or ".")):
        full = os.path.join(os.path.dirname(base_path) or ".", f)
        if re.match(re.escape(os.path.basename(base)) + r"_(c\d+r\d+|c\d+|r\d+)" + re.escape(ext) + r"$", f):
            if full not in files:
                files.append(full)
    return files

def load_coords(path):
    files = collect_part_files(path)
    dfs   = [pd.read_csv(fp) for fp in files]
    df    = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
    return {row["cell_id"]: (row["easting"], row["northing"])
            for _, row in df.iterrows()}

def load_ts(path):
    meta_cols = ["stress_period", "timestep", "ts_end_date", "sp_end_date"]
    base, ext = os.path.splitext(path)
    folder    = os.path.dirname(path) or "."
    base_name = os.path.basename(base)
    # group part files by col chunk
    col_chunks = {}
    if os.path.exists(path):
        col_chunks.setdefault("c1", []).insert(0, path)
    for f in sorted(os.listdir(folder)):
        full = os.path.join(folder, f)
        m = re.match(re.escape(base_name) + r"_(c(\d+)r(\d+)|c(\d+)|r(\d+))" + re.escape(ext) + r"$", f)
        if not m:
            continue
        tag = m.group(1)
        if re.match(r"c\d+r\d+", tag):
            cidx = int(re.search(r"c(\d+)", tag).group(1))
            key  = f"c{cidx}"
        elif re.match(r"c\d+$", tag):
            cidx = int(re.search(r"c(\d+)", tag).group(1))
            key  = f"c{cidx}"
        else:
            key  = "c1"
        col_chunks.setdefault(key, []).append(full)
    if not col_chunks:
        raise FileNotFoundError(f"No files found for: {path}")
    # for each col chunk, sort and concat rows vertically
    col_dfs = []
    for key in sorted(col_chunks.keys(), key=lambda x: int(x[1:])):
        parts  = sorted(col_chunks[key])
        frames = [pd.read_csv(fp) for fp in parts]
        merged = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        col_dfs.append(merged)
    # join col chunks horizontally on meta cols
    if len(col_dfs) == 1:
        df = col_dfs[0]
    else:
        df = col_dfs[0]
        for cdf in col_dfs[1:]:
            extra = [c for c in cdf.columns if c not in meta_cols]
            df    = df.join(cdf[extra], how="left")
    cell_cols = [c for c in df.columns if c not in meta_cols]
    df["sp_end_date"] = pd.to_datetime(
        df["sp_end_date"], format="%d/%m/%Y", errors="coerce")
    return df, cell_cols


def apply_filter(df, flt):
    mode = flt["filter_mode"]
    sp   = df["stress_period"]
    ts   = df["timestep"]
    dt   = df["sp_end_date"]
    if mode == "date_range":
        d1 = pd.to_datetime(flt["date_start"], format="%d/%m/%Y")
        d2 = pd.to_datetime(flt["date_end"],   format="%d/%m/%Y")
        return (dt >= d1) & (dt <= d2)
    elif mode == "sp_range":
        return (sp >= flt["sp_start"]) & (sp <= flt["sp_end"])
    elif mode == "sp_ts":
        start = (sp > flt["sp_ts_start_sp"]) | \
                ((sp == flt["sp_ts_start_sp"]) & (ts >= flt["sp_ts_start_ts"]))
        end   = (sp < flt["sp_ts_end_sp"]) | \
                ((sp == flt["sp_ts_end_sp"]) & (ts <= flt["sp_ts_end_ts"]))
        return start & end
    raise ValueError(f"Unknown filter_mode: {mode}")


def get_sp_last_ts(df_full, cell_cols, sp):
    mask = df_full["stress_period"] == sp
    if not mask.any():
        print(f"   WARNING: SP{sp} not found.")
        return None
    return df_full[cell_cols].loc[df_full[mask].index[-1]]

def calculate_fdc(df_cells, coord_lookup, percentiles, scale, method):
    """
    method: 'weibull' (type6/PERCENTILE.EXC) or 'linear' (type7/PERCENTILE.INC)
    """
    rows = []
    for cell_id in sort_cell_ids(df_cells.columns.tolist()):
        series = df_cells[cell_id].dropna().values.astype(float)
        e, n   = coord_lookup.get(cell_id, (None, None))
        row    = {"cell_id": cell_id, "easting": e, "northing": n}
        for q in percentiles:
            row[f"q{q}"] = round(
                np.percentile(series, 100 - q, method=method) / scale, 4)
        rows.append(row)
    return pd.DataFrame(rows).set_index("cell_id")


### Function changed here to compute run1-run2, or v1-v2
### Earlier it was (float(v2) - float(v1), 4)


def safe_diff(v2, v1):
    if v1 is None or v2 is None: return None
    return round(float(v1) - float(v2), 4)

### Function changed here to compute run1-run2, or v1-v2, or baseline-scenario for project plots
### Earlier it was round((v2f - v1f) / v1f * 100, 4)

def safe_pct(v2, v1):
    if v1 is None or v2 is None: return None
    v1f, v2f = float(v1), float(v2)
    if v1f == 0: return None
    return round((v1f - v2f) / v1f * 100, 4)

def autofit(ws):
    for col in ws.columns:
        mx = max((len(str(c.value)) for c in col if c.value is not None),
                 default=10)
        ws.column_dimensions[col[0].column_letter].width = min(mx + 3, 22)

def build_comparison(all_cells, coord_lookup,
                     sp_run1, sp_run2,
                     df_fdc1, df_fdc2,
                     run1, run2,
                     stress_periods, percentiles):

    rows = []
    for cell_id in sort_cell_ids(all_cells):
        e, n = coord_lookup.get(cell_id, (None, None))
        row  = {"id": cell_id, "easting": e, "northing": n}

        # Run1 SP values
        for sp in stress_periods:                ## Hardcode run1 and run2 for efficient Arcpro usage
            s = sp_run1.get(sp)
            row[f"run1_sp{sp}"] = (
               round(float(s[cell_id]) / FDC_SCALE,4)     ###Changes made by ankush to GET SP timeseries in MLD by dividing m3/day by 1000
               if (s is not None and cell_id in s.index)
               else None
                     )

        # Run1 FDC
        for q in percentiles:
            row[f"q{q}_run1"] = df_fdc1.loc[cell_id, f"q{q}"] if (
                cell_id in df_fdc1.index) else None


        # Run2 SP values
        for sp in stress_periods:
            s = sp_run2.get(sp)
            row[f"run2_sp{sp}"] = (
                round(float(s[cell_id]) / FDC_SCALE, 4)     ###Changes made by ankush to GET SP timeseries in MLD by dividing m3/day by 1000
                if (s is not None and cell_id in s.index)
                else None
            )

        # Run2 FDC
        for q in percentiles:
            row[f"q{q}_run2"] = df_fdc2.loc[cell_id, f"q{q}"] if (
                cell_id in df_fdc2.index) else None

        # SP Diff
        for sp in stress_periods:
            row[f"diff_sp{sp}"] = safe_diff(
                row.get(f"run2_sp{sp}"), row.get(f"run1_sp{sp}"))

        # FDC Diff
        for q in percentiles:
            row[f"q{q}_diff"] = safe_diff(
                row.get(f"q{q}_run2"), row.get(f"q{q}_run1"))

        # % Change — always last
        for q in percentiles:
            row[f"perc_q{q}diff"] = safe_pct(
                row.get(f"q{q}_run2"), row.get(f"q{q}_run1"))

        rows.append(row)
    return pd.DataFrame(rows)


def write_excel(path, df_fdc1, df_fdc2, df_comp, run1, run2, units=""):
    readme_rows = [
        {"property": "property description", "description": META.get("property_description", ""), "shp_descp": META.get("property_description", "")},
        {"property": "run1",                 "description": run1,                                  "shp_descp": "r1"},
        {"property": "run2",                 "description": run2,                                  "shp_descp": "r2"},
        {"property": "q",                    "description": "quantile",                            "shp_descp": "q"},
        {"property": "perc",                 "description": "percentage",                          "shp_descp": "p"},
        {"property": "diff",                 "description": "difference",                          "shp_descp": "d"},
        {"property": "sp",                   "description": "stress period",                       "shp_descp": "s"},
        {"property": "units",                "description": units,                                 "shp_descp": units},
        {"property": "NOTE:",               "description": "diff=r1-r2",                          "shp_descp": "diff=r1-r2"},
        {"property": "NOTE : ",              "description": "all differences computed as run1 - run2", "shp_descp": "all differences computed as run1 - run2"},

    ]
    df_readme = pd.DataFrame(readme_rows, columns=["property", "description", "shp_descp"])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df_fdc1.to_excel(writer, sheet_name=f"fdc_{run1}", index=True)
        df_fdc2.to_excel(writer, sheet_name=f"fdc_{run2}", index=True)
        df_comp.to_excel(writer, sheet_name="comparison",  index=False)
        df_readme.to_excel(writer, sheet_name="readme",    index=False)
        ws = writer.sheets["comparison"]
        # Find next empty row
        start_row = len(df_comp)



        for name in [f"fdc_{run1}", f"fdc_{run2}", "comparison", "readme"]:
            autofit(writer.sheets[name])
    print(f"   Saved: {path}")


# SHAPEFILE COLUMN SHORTENER
def shorten_col_names(columns, run1, run2):
    """
    Abbreviate column names to fit 10-char DBF limit and to keep them unique.
    e.g. molmf98 -> mo98, perc_ -> pc_
    """
    def abbrev_run(name, run):
        digits = re.sub(r'\D', '', run)
        prefix = run[:2]
        return name.replace(run, prefix + digits)

    shortened = {}
    for col in columns:
        s = col
        s = abbrev_run(s, run1)
        s = abbrev_run(s, run2)
        s = s.replace("perc_", "p_")
        s = s.replace("diff_", "d_")
        s = s.replace("_diff", "_d")
        s = s.replace("diff",  "d")
        s = s.replace("_sp",   "_s")
        s = s.replace("sp_",   "s_")
        s = s.replace("run1",  "r1")
        s = s.replace("run2",  "r2")
        s = s[:10]
        shortened[col] = s

    # Ensure uniqueness
    seen   = {}
    result = {}
    for orig, short in shortened.items():
        if short in seen.values():
            base = short[:8]
            i    = 2
            candidate = f"{base}_{i}"
            while candidate in seen.values():
                i += 1
                candidate = f"{base}_{i}"
            short = candidate
        seen[orig]   = short
        result[orig] = short
    return result


# LOAD COORDINATES
print("\nLoading coordinates ...")
fo_coords = load_coords(INPUTS["flowout_coords_csv"])
lk_coords = load_coords(INPUTS["leakage_coords_csv"])
print(f"   Flowout : {len(fo_coords):,}  |  Leakage : {len(lk_coords):,}")


# LOAD TIMESERIES
print("\nLoading timeseries ...")
df_full1_fo, cc1_fo = load_ts(INPUTS["run1_flowout_csv"])
df_full2_fo, cc2_fo = load_ts(INPUTS["run2_flowout_csv"])
df_full1_lk, cc1_lk = load_ts(INPUTS["run1_leakage_csv"])
df_full2_lk, cc2_lk = load_ts(INPUTS["run2_leakage_csv"])
print(f"   Run1 flowout : {len(df_full1_fo):,} rows x {len(cc1_fo):,} cells")
print(f"   Run2 flowout : {len(df_full2_fo):,} rows x {len(cc2_fo):,} cells")
print(f"   Run1 leakage : {len(df_full1_lk):,} rows x {len(cc1_lk):,} cells")
print(f"   Run2 leakage : {len(df_full2_lk):,} rows x {len(cc2_lk):,} cells")

# CELL SELECTION MODES
# Both all_cells and specified_cells can be true at the same time — in that
# case the full analysis (filter -> FDC -> excel -> shapefile -> maps -> plots)
# runs once per mode, each writing into its own output subfolder:
#   fdc_output_all_cells      (all_cells: true)
#   fdc_output_selected_cells (specified_cells: true)
_cell_sel = INPUTS.get("cell_selection", {})
CELL_MODES = []
if _cell_sel.get("all_cells", True):
    CELL_MODES.append(("all_cells", "fdc_output_all_cells"))
if _cell_sel.get("specified_cells", False):
    CELL_MODES.append(("selected_cells", "fdc_output_selected_cells"))
if not CELL_MODES:
    CELL_MODES.append(("all_cells", "fdc_output_all_cells"))

print(f"\nCell selection mode(s) to run: {[m[0] for m in CELL_MODES]}")

# Name lookup for subplot titles (selected_cells_csv provides name + cell_id)
NAME_LOOKUP = {}
_spec_csv_path = _cell_sel.get("specified_cells_csv", "")
if _spec_csv_path and os.path.exists(_spec_csv_path):
    _name_df = pd.read_csv(_spec_csv_path)
    if "name" in _name_df.columns and "cell_id" in _name_df.columns:
        NAME_LOOKUP = dict(zip(_name_df["cell_id"].astype(str), _name_df["name"].astype(str)))

# Keep the originally-loaded (unfiltered) cell-column lists so each mode
# below starts from the full set, independent of any other mode's filtering.
_cc1_fo_ALL, _cc2_fo_ALL = cc1_fo, cc2_fo
_cc1_lk_ALL, _cc2_lk_ALL = cc1_lk, cc2_lk

for MODE_KEY, MODE_SUBDIR in CELL_MODES:
    print("\n" + "#" * 60)
    print(f"# CELL SELECTION MODE: {MODE_KEY}")
    print("#" * 60)

    # Per-mode output folder
    OUTPUT_DIR = os.path.join(BASE_OUTPUT_DIR, MODE_SUBDIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    OUT_FLOWOUT = os.path.join(OUTPUT_DIR,
        f"{model_lower}_{RUN1}_vs_{RUN2}_{sp_range_str}_fdc_flowout.xlsx")
    OUT_LEAKAGE = os.path.join(OUTPUT_DIR,
        f"{model_lower}_{RUN1}_vs_{RUN2}_{sp_range_str}_fdc_leakage.xlsx")
    print(f"   Output folder    : {OUTPUT_DIR}")

    # Reset cell-column lists to the full set before applying this mode's selection
    cc1_fo, cc2_fo = list(_cc1_fo_ALL), list(_cc2_fo_ALL)
    cc1_lk, cc2_lk = list(_cc1_lk_ALL), list(_cc2_lk_ALL)

    if MODE_KEY == "selected_cells":
        _spec_path = _cell_sel.get("specified_cells_csv", "")
        if not os.path.exists(_spec_path):
            print(f"   ERROR: specified_cells_csv not found: {_spec_path}")
            sys.exit(1)
        _spec_ids = set(pd.read_csv(_spec_path)["cell_id"].astype(str).tolist())
        print(f"   Cell selection   : specified_cells — {len(_spec_ids):,} cells from {_spec_path}")
        cc1_fo = [c for c in cc1_fo if c in _spec_ids]
        cc2_fo = [c for c in cc2_fo if c in _spec_ids]
        cc1_lk = [c for c in cc1_lk if c in _spec_ids]
        cc2_lk = [c for c in cc2_lk if c in _spec_ids]
    else:
        print("   Cell selection   : all_cells")


    # APPLY FILTER
    print(f"\nApplying filter: {FILTER['filter_mode']} ...")

    def filter_cells(df_full, cell_cols):
        mask     = apply_filter(df_full, FILTER)
        filtered = df_full[mask]
        print(f"   {len(filtered):,} / {len(df_full):,} rows kept")
        return filtered[cell_cols].copy()

    cells1_fo = filter_cells(df_full1_fo, cc1_fo)
    cells2_fo = filter_cells(df_full2_fo, cc2_fo)
    cells1_lk = filter_cells(df_full1_lk, cc1_lk)
    cells2_lk = filter_cells(df_full2_lk, cc2_lk)


    # FDC CALCULATION AND EXCEL OUTPUT
    df_fdc_fo1 = df_fdc_fo2 = df_fdc_lk1 = df_fdc_lk2 = None
    df_comp_fo = df_comp_lk = None

    if FDC_CFG["run_analysis"]:
        print(f"\nCalculating FDC ({PCT_TYPE} / numpy {PCT_METHOD}) ...")
        df_fdc_fo1 = calculate_fdc(cells1_fo, fo_coords, PERCENTILES, FDC_SCALE, PCT_METHOD)
        df_fdc_fo2 = calculate_fdc(cells2_fo, fo_coords, PERCENTILES, FDC_SCALE, PCT_METHOD)
        df_fdc_lk1 = calculate_fdc(cells1_lk, lk_coords, PERCENTILES, FDC_SCALE, PCT_METHOD)
        df_fdc_lk2 = calculate_fdc(cells2_lk, lk_coords, PERCENTILES, FDC_SCALE, PCT_METHOD)
        print("   Done.")

        print(f"\nExtracting SP values at {SPS} ...")
        sp_qt1, sp_qt2, sp_gw1, sp_gw2 = {}, {}, {}, {}
        for sp in SPS:
            sp_qt1[sp] = get_sp_last_ts(df_full1_fo, cc1_fo, sp)
            sp_qt2[sp] = get_sp_last_ts(df_full2_fo, cc2_fo, sp)
            sp_gw1[sp] = get_sp_last_ts(df_full1_lk, cc1_lk, sp)
            sp_gw2[sp] = get_sp_last_ts(df_full2_lk, cc2_lk, sp)

        print("\nBuilding comparison tables ...")
        all_fo = sort_cell_ids(list(set(cc1_fo) | set(cc2_fo)))
        all_lk = sort_cell_ids(list(set(cc1_lk) | set(cc2_lk)))

        df_comp_fo = build_comparison(
            all_fo, fo_coords, sp_qt1, sp_qt2,
            df_fdc_fo1, df_fdc_fo2, RUN1, RUN2, SPS, PERCENTILES)
        df_comp_lk = build_comparison(
            all_lk, lk_coords, sp_gw1, sp_gw2,
            df_fdc_lk1, df_fdc_lk2, RUN1, RUN2, SPS, PERCENTILES)

        print(f"   Flowout : {len(df_comp_fo):,} rows x {len(df_comp_fo.columns):,} cols")
        print(f"   Leakage : {len(df_comp_lk):,} rows x {len(df_comp_lk.columns):,} cols")

        print("\nWriting Excel files ...")
        write_excel(OUT_FLOWOUT, df_fdc_fo1, df_fdc_fo2, df_comp_fo, RUN1, RUN2, META.get("units", {}).get("flowout", ""))
        write_excel(OUT_LEAKAGE, df_fdc_lk1, df_fdc_lk2, df_comp_lk, RUN1, RUN2, META.get("units", {}).get("leakage", ""))
    else:
        print("\nFDC analysis skipped (run_analysis: false)")
        if os.path.exists(OUT_FLOWOUT) and os.path.exists(OUT_LEAKAGE):
            print("   Loading existing Excel files for plotting ...")
            _xfo = pd.ExcelFile(OUT_FLOWOUT)
            _xlk = pd.ExcelFile(OUT_LEAKAGE)
            df_fdc_fo1 = _xfo.parse(f"fdc_{RUN1}", index_col=0)
            df_fdc_fo2 = _xfo.parse(f"fdc_{RUN2}", index_col=0)
            df_fdc_lk1 = _xlk.parse(f"fdc_{RUN1}", index_col=0)
            df_fdc_lk2 = _xlk.parse(f"fdc_{RUN2}", index_col=0)
            df_comp_fo = _xfo.parse("comparison")
            df_comp_lk = _xlk.parse("comparison")
            print(f"   Flowout : {len(df_comp_fo):,} rows  |  Leakage : {len(df_comp_lk):,} rows")
        else:
            missing = [f for f in [OUT_FLOWOUT, OUT_LEAKAGE] if not os.path.exists(f)]
            print(f"   Excel files not found — run_analysis must be true first:")
            for m in missing:
                print(f"     {m}")


    # FDC PLOT HELPERS
    def make_label(cid, run, mode):
        if mode == "cell_id":
            return f"{cid} ({run})"
        elif mode == "layer_row_col":
            p = cid.split("_")
            return f"L{p[1]}_R{p[2]}_C{p[3]} ({run})"
        else:
            # Legend displaying run only
            # p = cid.split("_")
            # return f"{cid} | L{p[1]}_R{p[2]}_C{p[3]} ({run})"
            return f"{run}"

    def get_fdc_row(df_fdc, cid, run, percentiles, pmin, pmax):
        if df_fdc is None or cid not in df_fdc.index:
            print(f"   INFO: Cell {cid} not available in {run} — curve skipped.")
            return None, None
        plot_pcts = [q for q in percentiles if pmin <= q <= pmax]
        y = [df_fdc.loc[cid, f"q{q}"] for q in plot_pcts]
        return plot_pcts, y


    def draw_ax(ax, curves, title, pmin, pmax, percentiles):
        # for label, x_vals, y_vals, color in curves:
        #       ax.plot(x_vals, y_vals, label=label, color=color, linewidth=LINE_WIDTH, marker=None)
         markers = ["","","o", "s",  "D", "x", "*"]  # define marker styles
         linestyles = ["-", "--", "-.", ":"]
         # linestyles = ["-", ":", "--", "-."]
         line_widths = [LINE_WIDTH, 0.90*LINE_WIDTH, 2, 2.5, 3, 1.75, 2.25]

         for i, (label, x_vals, y_vals, color) in enumerate(curves):
            ax.plot(x_vals, y_vals,
                    label=label,
                    color=color,
                    # linewidth=LINE_WIDTH,
                    linewidth=line_widths[i % len(line_widths)],
                    linestyle=linestyles[i % len(linestyles)],
                    marker=markers[i % len(markers)],
                    markersize=7)

            ax.set_xlabel("% Time Exceeded",
                          fontsize=AXIS_LABEL_FONTSIZE, fontweight="normal")
            ax.set_ylabel("Flow (Ml/d)",
                          fontsize=AXIS_LABEL_FONTSIZE, fontweight="normal")
            ## for long title names we want 2 rows
            # ax.set_title(title, fontsize=TITLE_FONTSIZE, fontweight="normal")

            # title_display = textwrap.fill(title, width=40) if len(title) > 40 else title
            # ax.set_title(title_display, fontsize=TITLE_FONTSIZE, fontweight="normal", multialignment="center",y=1.2)   #move title upward with y=1.05, 1.15 so to keep figure height same for all plots

            title_display = textwrap.fill(title, width=40)

            if "\n" not in title_display:
                title_display += "\n"  # reserve second line

            ax.set_title(title_display, fontsize=TITLE_FONTSIZE, fontweight="normal", multialignment="center")
            # ax.set_title(title_display)

            ax.tick_params(axis="both", labelsize=TICK_LABEL_FONTSIZE)
            ax.legend(fontsize=LEGEND_FONTSIZE, framealpha=0.3)
            ax.set_xticks([q for q in percentiles if pmin <= q <= pmax])
            ax.set_xticklabels([q for q in percentiles if pmin <= q <= pmax], rotation=90, ha="center")
            ax.tick_params(axis="x", labelsize=TICK_LABEL_FONTSIZE * 0.92)
            ax.grid(True, alpha=0.7)


    def get_fdc_tables(flow_type):
        if flow_type == "flowout": return df_fdc_fo1, df_fdc_fo2
        if flow_type == "leakage": return df_fdc_lk1, df_fdc_lk2
        return None, None


    def get_fdc_for_run(flow_type, run):
        if flow_type == "flowout":
            return df_fdc_fo1 if run == RUN1 else df_fdc_fo2
        return df_fdc_lk1 if run == RUN1 else df_fdc_lk2

    COLORS = ["tomato", "lightseagreen","lightcoral", "grey","maroon", "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    pmin   = PLOT_CFG.get("percentile_plot_min", 1)
    pmax   = PLOT_CFG.get("percentile_plot_max", 99)
    label_mode = PLOT_CFG["label_style"]

    sp1_cfg = PLOT_CFG.get("subplot1", {})
    sp2_cfg = PLOT_CFG.get("subplot2", {})

    show_sp1 = sp1_cfg.get("enabled", False) and (
        (sp1_cfg.get("flow_type") == "flowout" and PLOT_CFG["plot_flowout"]) or
        (sp1_cfg.get("flow_type") == "leakage" and PLOT_CFG["plot_leakage"]))

    show_sp2 = sp2_cfg.get("enabled", False) and (
        (sp2_cfg.get("flow_type") == "flowout" and PLOT_CFG["plot_flowout"]) or
        (sp2_cfg.get("flow_type") == "leakage" and PLOT_CFG["plot_leakage"]))

    if show_sp1 or show_sp2:
        print("\nGenerating FDC plots ...")


    # --- Subplot 1: same cell, Run1 vs Run2 ---
    if show_sp1:
        ftype    = sp1_cfg["flow_type"]
        sp1_mode = sp1_cfg.get("mode", "single")   # single | all

        if sp1_mode == "all":
            sp1_cell_ids = list(NAME_LOOKUP.keys())
        else:
            sp1_cell_ids = [sp1_cfg["cell_id"]]

        dff1, dff2        = get_fdc_tables(ftype)
        base_fn, ext_fn   = os.path.splitext(sp1_cfg["plot_filename"])

        for cid in sp1_cell_ids:
            name     = NAME_LOOKUP.get(cid, "")
            # title_id = f"{name} ({cid})" if name else cid
            title_id = name if name else cid
            curves   = []
            for i, (run, dff) in enumerate([(RUN1, dff1), (RUN2, dff2)]):
                x, y = get_fdc_row(dff, cid, run, PERCENTILES, pmin, pmax)
                if x:
                    curves.append((make_label(cid, run, label_mode), x, y, COLORS[i]))
            if curves:
                plt.style.use("classic")
                fig, ax = plt.subplots(figsize=FIGURE_SIZE)

                # draw_ax(ax, curves,
                #         f"FDC {ftype.capitalize()} {title_id} {RUN1} vs {RUN2}",
                #         pmin, pmax, PERCENTILES)
                # Title of plots changed based on request
                draw_ax(ax, curves,
                        title_id, pmin, pmax, PERCENTILES)

                ax.legend(fontsize=LEGEND_FONTSIZE, title_fontsize=LEGEND_FONTSIZE)
                plt.tight_layout()
                if sp1_mode == "all":
                    out_p = os.path.join(OUTPUT_DIR, f"{base_fn}_{cid}{ext_fn}")
                else:
                    out_p = os.path.join(OUTPUT_DIR, sp1_cfg["plot_filename"])
                plt.savefig(out_p, dpi=1000)
                # plt.pause(1)
                print(f"   Subplot1 saved: {out_p}")
                plt.close(fig)


    # --- Subplot 2: same run, two different cell IDs ---
    if show_sp2:
        ftype  = sp2_cfg["flow_type"]
        run    = sp2_cfg["run"]
        cid1   = sp2_cfg["cell_id_1"]
        cid2   = sp2_cfg["cell_id_2"]
        dff    = get_fdc_for_run(ftype, run)
        curves = []
        for i, cid in enumerate([cid1, cid2]):
            x, y = get_fdc_row(dff, cid, run, PERCENTILES, pmin, pmax)
            if x:
                curves.append((make_label(cid, run, label_mode), x, y, COLORS[i]))
        if curves:
            plt.style.use("fivethirtyeight")
            fig, ax = plt.subplots(figsize=FIGURE_SIZE)
            draw_ax(ax, curves,
                    f"FDC {ftype.capitalize()} {run} {cid1} vs {cid2}",
                    pmin, pmax, PERCENTILES)
            ax.legend(fontsize=LEGEND_FONTSIZE, title_fontsize=LEGEND_FONTSIZE)
            plt.tight_layout()
            out_p = os.path.join(OUTPUT_DIR, sp2_cfg["plot_filename"])
            plt.savefig(out_p, dpi=500)
            # plt.pause(1)
            print(f"   Subplot2 saved: {out_p}")


    # SHAPEFILE OUTPUT

    def save_shapefile(df_comp, columns, shp_name, label, save_all=False, units=""):
        try:
            import geopandas as gpd
            from shapely.geometry import Point
        except ImportError:
            print("   ERROR: geopandas/shapely not installed.")
            print("   Run: pip install geopandas shapely")
            return

        if save_all:
            # Save entire comparison sheet as shapefile attributes
            available   = [c for c in df_comp.columns if c not in ["id", "easting", "northing"]]
            print(f"   Saving ALL {len(available)} columns from comparison sheet.")
        else:
            available = [c for c in columns if c in df_comp.columns]
            missing   = [c for c in columns if c not in df_comp.columns]
            if missing:
                print(f"   WARNING: columns not found — skipped: {missing}")

        cols_to_use = ["id", "easting", "northing"] + available
        df_shp = df_comp[cols_to_use].copy().dropna(subset=["easting", "northing"])

        rename_map = shorten_col_names(df_shp.columns.tolist(), RUN1, RUN2)
        renamed    = {k: v for k, v in rename_map.items() if k != v}
        if renamed:
            print(f"   NOTE: Column names shortened for 10-char DBF limit:")
            for orig, short in renamed.items():
                print(f"     {orig:<25s} -> {short}")
        df_shp = df_shp.rename(columns=rename_map)

        geometry = [Point(e, n) for e, n in zip(df_shp["easting"], df_shp["northing"])]
        gdf      = gpd.GeoDataFrame(df_shp, geometry=geometry, crs="EPSG:27700")

        shp_meta = [
            ("property description", META.get("property_description", ""), META.get("property_description", "")),
            ("run1",                 RUN1,                                  "r1"),
            ("run2",                 RUN2,                                  "r2"),
            ("q",                    "quantile",                            "q"),
            ("perc",                 "percentage",                          "p"),
            ("diff",                 "difference",                          "d"),
            ("sp",                   "stress period",                       "s"),
            ("units",                units,                                 units),
            ("NOTE:",                "diff=run1-run2",                   "diff=run1-run2"),
        ]
        gdf["property"]    = ""
        gdf["description"] = ""
        gdf["shp_descp"]   = ""
        for i, (prop, desc, shp) in enumerate(shp_meta):
            if i < len(gdf):
                gdf.iloc[i, gdf.columns.get_loc("property")]    = prop
                gdf.iloc[i, gdf.columns.get_loc("description")] = desc
                gdf.iloc[i, gdf.columns.get_loc("shp_descp")]   = shp

        out_path = os.path.join(OUTPUT_DIR, shp_name)
        gdf.to_file(out_path)
        print(f"   {label} shapefile saved: {out_path}")
        print(f"   {len(gdf):,} points  |  {len(available)} attribute cols  |  CRS: EPSG:27700")


    if SHP_CFG["save_flowout_shapefile"] and df_comp_fo is not None:
        print("\nSaving flowout shapefile ...")
        save_shapefile(df_comp_fo, SHP_CFG.get("flowout_columns", []),
                       SHP_CFG.get("flowout_shp_name",
                       f"{model_lower}_{RUN1}_vs_{RUN2}_{sp_range_str}_flowout.shp"),
                       "Flowout",
                       save_all=SHP_CFG.get("save_all_columns", False),
                       units=META.get("units", {}).get("flowout", ""))

    if SHP_CFG["save_leakage_shapefile"] and df_comp_lk is not None:
        print("\nSaving leakage shapefile ...")
        save_shapefile(df_comp_lk, SHP_CFG.get("leakage_columns", []),
                       SHP_CFG.get("leakage_shp_name",
                       f"{model_lower}_{RUN1}_vs_{RUN2}_{sp_range_str}_leakage.shp"),
                       "Leakage",
                       save_all=SHP_CFG.get("save_all_columns", False),
                       units=META.get("units", {}).get("leakage", ""))

    # MAP PLOT 
    def save_map_plot(df_comp, plot_col, map_file, title_label, basemap_type, cmap):
        try:
            import geopandas as gpd
            from shapely.geometry import Point
        except ImportError:
            print("   ERROR: geopandas/shapely not installed.")
            return

        if plot_col not in df_comp.columns:
            print(f"   ERROR: Column '{plot_col}' not found — map skipped.")
            return

        df_map   = df_comp[["id", "easting", "northing", plot_col]].dropna()
        geometry = [Point(e, n) for e, n in zip(df_map["easting"], df_map["northing"])]
        gdf      = gpd.GeoDataFrame(df_map, geometry=geometry, crs="EPSG:27700")

        if basemap_type != "none":
            try:
                import contextily as ctx
                gdf_wm = gdf.to_crs(epsg=3857)
                mpl.rcParams.update(mpl.rcParamsDefault)
                fig, ax = plt.subplots(figsize=MAP_FIGURE_SIZE)
                gdf_wm.plot(ax=ax, column=plot_col, cmap=cmap,
                            markersize=MAP_POINT_SIZE, legend=True,
                            legend_kwds={"label": plot_col, "shrink": 0.75})

                cbar_ax = ax.get_figure().axes[-1]
                cbar_ax.set_ylabel(plot_col, fontsize=16)
                cbar_ax.tick_params(labelsize=14)

                if basemap_type == "esri_satellite":
                    ctx.add_basemap(ax, source=ctx.providers.Esri.WorldImagery)
                elif basemap_type == "osm":
                    ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
                ax.set_title(f"{title_label} {plot_col}",
                             fontsize=TITLE_FONTSIZE, fontweight="normal")
                ax.tick_params(labelsize=TICK_LABEL_FONTSIZE)

                ax.set_xlabel("Web Mercator X (m)", fontsize=AXIS_LABEL_FONTSIZE)
                ax.set_ylabel("Web Mercator Y (m)", fontsize=AXIS_LABEL_FONTSIZE)

                ax.grid(False)
                plt.tight_layout()
                out_path = os.path.join(OUTPUT_DIR, map_file)
                fig.savefig(out_path, dpi=500)
                # plt.pause(1)
                print(f"   Map plot saved: {out_path}")
                return
            except ImportError:
                print("   WARNING: contextily not installed — saving without basemap.")
                print("   Run: pip install contextily")

        # No basemap fallback
        mpl.rcParams.update(mpl.rcParamsDefault)
        fig, ax = plt.subplots(figsize=MAP_FIGURE_SIZE)
        gdf.plot(ax=ax, column=plot_col, cmap=cmap,
                 markersize=MAP_POINT_SIZE, legend=True,
                 legend_kwds={"label": plot_col, "shrink": 0.7})

        cbar_ax = ax.get_figure().axes[-1]
        cbar_ax.set_ylabel(plot_col, fontsize=16)
        cbar_ax.tick_params(labelsize=14)

        ax.set_title(f"{title_label} — {plot_col}",
                     fontsize=TITLE_FONTSIZE, fontweight="normal")
        ax.tick_params(labelsize=TICK_LABEL_FONTSIZE)
        ax.set_xlabel("Easting (BNG)", fontsize=AXIS_LABEL_FONTSIZE)
        ax.set_ylabel("Northing (BNG)", fontsize=AXIS_LABEL_FONTSIZE)

        ax.grid(False)
        plt.tight_layout()
        out_path = os.path.join(OUTPUT_DIR, map_file)
        fig.savefig(out_path, dpi=500)
        # plt.pause(1)
        print(f"   Map plot saved: {out_path}")


    if MAP_CFG["plot_flowout_map"] and df_comp_fo is not None:
        print("\nGenerating flowout map plot ...")
        map_file = MAP_CFG.get("flowout_map_file",
                   f"{model_lower}_{RUN1}_vs_{RUN2}_{sp_range_str}_flowout_map.png")
        save_map_plot(df_comp_fo, MAP_CFG["flowout_map_col"],
                      map_file, f"{MODEL} Stream Flow Out",
                      MAP_CFG["basemap"], MAP_CFG["colormap"])

    if MAP_CFG["plot_leakage_map"] and df_comp_lk is not None:
        print("\nGenerating leakage map plot ...")
        map_file = MAP_CFG.get("leakage_map_file",
                   f"{model_lower}_{RUN1}_vs_{RUN2}_{sp_range_str}_leakage_map.png")
        save_map_plot(df_comp_lk, MAP_CFG["leakage_map_col"],
                      map_file, f"{MODEL} Stream Leakage",
                      MAP_CFG["basemap"], MAP_CFG["colormap"])

    # SUMMARY
    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)
    if FDC_CFG["run_analysis"]:
        print(f"  {OUT_FLOWOUT}")
        print(f"  {OUT_LEAKAGE}")
    print("=" * 60)
