"""
MODFLOW ANALYSIS — MASTER RUNNER  (cauvery MODEL)
Written By: Ankush Kaundal
Reads config.yaml and runs whichever scripts are enabled.
All scripts and config.yaml must be in the same folder as this file.
Usage:
  python run_all.py
"""

import sys
import os
import time
import subprocess

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from config_loader import load_config

cfg = load_config("config.yaml")

print("=" * 60)
print("MODFLOW ANALYSIS — MASTER RUNNER")
print("=" * 60)
print(f"  Model      : {cfg['model_name']}")
print(f"  Run        : {cfg['run_number']}")
print(f"  Scripts in : {_here}")
print(f"\n  Scripts to run:")
print(f"    cell_coordinates : {'YES' if cfg['cell_coordinates']['run'] else 'skip'}")
print(f"    dis_timing       : {'YES' if cfg['dis_timing']['run'] else 'skip'}")
print(f"    cs1_analysis     : {'YES' if cfg['cs1_analysis']['run'] else 'skip'}")
print(f"    cs2_analysis     : {'YES' if cfg['cs2_analysis']['run'] else 'skip'}")
print("=" * 60)

scripts = [
    ("cell_coordinates", "generate_cell_coordinates.py"),
    ("dis_timing",       "tdis_to_datetime_stress_periods.py"),
    ("cs1_analysis",     "cs1_final.py"),
    ("cs2_analysis",     "cs2_final.py"),
]

results   = {}
start_all = time.time()

for config_key, script_file in scripts:
    if cfg[config_key]["run"]:
        script_path = os.path.join(_here, script_file)
        print(f"\n>>> Running: {script_file}")
        t0     = time.time()
        result = subprocess.run([sys.executable, script_path])
        elapsed = time.time() - t0
        if result.returncode == 0:
            results[script_file] = f"OK ({elapsed:.1f}s)"
        else:
            results[script_file] = f"FAILED (exit code {result.returncode})"
    else:
        results[script_file] = "skipped"

print("\n" + "=" * 60)
print("RUN SUMMARY")
print("=" * 60)
for script, status in results.items():
    print(f"  {script:<45s} : {status}")
print(f"\n  Total time : {time.time() - start_all:.1f}s")
print("=" * 60)
