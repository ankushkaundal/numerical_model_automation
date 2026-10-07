# CONFIG LOADER
# Written By: Ankush Kaundal
# Reads config.yaml and provides helper functions used by all scripts for easy runs.
# Place this file in the same folder as all other scripts and config.yaml.

import yaml
import os
from datetime import date


def load_config(yaml_path="config.yaml"):
    """
    Load and return config.yaml as a dict.
    """
    if not os.path.isabs(yaml_path):
        yaml_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), yaml_path
        )
    if not os.path.exists(yaml_path):
        raise FileNotFoundError(
            f"config.yaml not found at: {yaml_path}\n"
            f"Make sure config.yaml is in the same folder as the scripts."
        )
    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)    # converts yaml file to python dictionary

    cfg = _resolve_placeholders(cfg)   # replace {model_root} {run_number} {model_name}
    cfg = _merge_shared(cfg)           # push shared grid/timing/paths into each section
    return cfg


def _resolve_placeholders(cfg):
    """Replace {model_root}, {run_number}, {model_name} in all string values."""
    model_root = str(cfg.get("model_root", ""))
    run_number = str(cfg.get("run_number", ""))
    model_name = str(cfg.get("model_name", ""))

    def resolve(val):
        if isinstance(val, str):
            return (val
                    .replace("{model_root}", model_root)
                    .replace("{run_number}", run_number)
                    .replace("{model_name}", model_name))
        elif isinstance(val, dict):
            return {k: resolve(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [resolve(v) for v in val]
        return val

    return {k: resolve(v) for k, v in cfg.items()}


def _merge_shared(cfg):
    """
    Push shared grid / timing / paths blocks into each script section
    so all scripts work without any changes.
      grid + timing  -> section['parameters']
      dis_file, cs1_file -> section['inputs']
      output_dir     -> section['outputs']
    Script-level values always win — shared values never overwrite.
    """
    shared_grid   = cfg.get("grid",   {}) or {}
    shared_timing = cfg.get("timing", {}) or {}
    shared_paths  = cfg.get("paths",  {}) or {}

    for key in ["cell_coordinates", "dis_timing", "cs1_analysis", "cs2_analysis"]:
        if key not in cfg or cfg[key] is None:
            cfg[key] = {}
        section = cfg[key]

        # parameters
        if section.get("parameters") is None:
            section["parameters"] = {}
        for k, v in {**shared_grid, **shared_timing}.items():
            if k not in section["parameters"]:
                section["parameters"][k] = v

        # inputs
        if section.get("inputs") is None:
            section["inputs"] = {}
        for k in ["dis_file", "cs1_file"]:
            if k not in section["inputs"] and k in shared_paths:
                section["inputs"][k] = shared_paths[k]

        # outputs
        if section.get("outputs") is None:
            section["outputs"] = {}
        if "output_dir" not in section["outputs"] and "output_dir" in shared_paths:
            section["outputs"]["output_dir"] = shared_paths["output_dir"]

    return cfg


def get_start_date(section_cfg):
    """Parse model_start_date string from a script section into a date object."""
    return date.fromisoformat(section_cfg["parameters"]["model_start_date"])


def output_path(model_name, output_dir, filename):
    """
    Build full output path with model_name prefix.
    Creates the output directory if it does not already exist.
    """
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{model_name}_{filename}")


def cell_centroid(row, col, params):
    """
    Compute British National Grid cell centroid (easting, northing) for 1-based row/col.
    params = the 'parameters' block from any script section in config.yaml.
    Supports all four origin corner types:
      bottom_left  — easting right, northing up
      top_left     — easting right, northing down
      bottom_right — easting left,  northing up
      top_right    — easting left,  northing down
    """
    nrow      = params["nrow"]
    ncol      = params["ncol"]
    cell_size = params["cell_size"]
    origin_e  = params["origin_easting"]
    origin_n  = params["origin_northing"]
    corner    = params["origin_corner"]
    half      = cell_size / 2

    if corner == "bottom_left":
        easting  = origin_e + (col - 1) * cell_size + half
        northing = origin_n + (nrow - row) * cell_size + half
    elif corner == "top_left":
        easting  = origin_e + (col - 1) * cell_size + half
        northing = origin_n - (row - 1) * cell_size - half
    elif corner == "bottom_right":
        easting  = origin_e - (ncol - col) * cell_size - half
        northing = origin_n + (nrow - row) * cell_size + half
    elif corner == "top_right":
        easting  = origin_e - (ncol - col) * cell_size - half
        northing = origin_n - (row - 1) * cell_size - half
    else:
        raise ValueError(
            f"Unknown origin_corner '{corner}'. "
            "Use: bottom_left | top_left | bottom_right | top_right"
        )
    return easting, northing
