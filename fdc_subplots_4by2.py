# Flow Duration Curve Mutli Plots (4x2) PNG generator (v1.0)
# Written By: Ankush Kaundal


#Notes: Calculate_fdc.py must be run beofre running this script.

from PIL import Image
import matplotlib.pyplot as plt
import pandas as pd
import os
import math

# input run numbers here - based on 2 runs you are working with and model outputs
model_name = "cauvery"
run1 = "cauvery401"   #Baseline
run2 = "cauvery405"   #Scenario
tags = ["4d", "4c", "4w", "4h"]  # list of tags to process in order (add/remove as needed, e.g. 5e for eden, 5d for darrent)

model_root = r"F:\cauvery_Update\2026_cauvery_project\GW\output"

# INPUT PATHS
img_folder = rf"{model_root}\{run2}\flows\fdc_output\fdc_output_selected_cells"

# OUTPUT PATH
output_folder = rf"{model_root}\{run2}\flows\fdc_output"

A4_WIDTH_IN = 8.27
A4_HEIGHT_IN = 11.69

panel_aspect = 6 / 8.5  # height / width of each individual panel

n_rows, n_cols = 4, 2

cell_h_max = A4_HEIGHT_IN / n_rows
cell_w_from_h = cell_h_max / panel_aspect
cell_w_from_width_limit = A4_WIDTH_IN / n_cols

cell_w = min(cell_w_from_h, cell_w_from_width_limit)
cell_h = cell_w * panel_aspect

fig_width = cell_w * n_cols
fig_height = cell_h * n_rows


# BUILD IMAGE PATH FOR EACH CELL ID
def image_path_for_cell(cell_id):
    filename = f"{model_name}_{run1}_vs_{run2}_fdc_subplot1_{cell_id}.png"
    return os.path.join(img_folder, filename)

# SPLIT CELL IDS INTO BATCHES OF 10 (5 rows x 2 cols per figure)
panels_per_fig = n_rows * n_cols

labels_full = [
    "(a)", "(b)", "(c)", "(d)", "(e)",
    "(f)", "(g)", "(h)", "(i)", "(j)"
]

# loop over each tag; tag-dependent paths are now built inside the loop
for tag in tags:

    selected_cells_file = f"selected_cells_cauvery_{tag}.csv"  # moved inside loop (depends on tag)
    cell_csv_path = rf"{model_root}\{run2}\flows\{selected_cells_file}"  # moved inside loop (depends on tag)
    output_base_name = f"fdc_panel_{tag}"  # moved inside loop (depends on tag)

    # READ CELL IDS (top to bottom, as in the CSV)
    cells_df = pd.read_csv(cell_csv_path)
    cell_ids = cells_df["cell_id"].tolist()

    n_batches = math.ceil(len(cell_ids) / panels_per_fig)  # moved inside loop (depends on cell_ids for this tag)

    for batch_idx in range(n_batches):

        batch_cells = cell_ids[batch_idx * panels_per_fig: (batch_idx + 1) * panels_per_fig]

        # LOAD IMAGES FOR THIS BATCH
        images = [Image.open(image_path_for_cell(cid)) for cid in batch_cells]
        labels = labels_full[:len(batch_cells)]

        # CREATE 4 x 2 FIGURE
        fig, axes = plt.subplots(
            n_rows, n_cols,
            figsize=(fig_width, fig_height),
            dpi=1000
        )

        plt.subplots_adjust(
            wspace=0.003,
            hspace=0.03
        )

        axes_ordered = axes.flatten()

        # PLOT PANELS
        for i, (ax, img, label) in enumerate(zip(axes_ordered, images, labels)):
            ax.imshow(img, aspect="auto")
            # ax.set_title(
            #     label,
            #     loc="left",
            #     fontsize=10,
            #     fontweight="bold",
            #     pad=3
            # )

            ax.axis("off")

        for ax in axes_ordered[len(images):]:
            ax.axis("off")

        output_path = os.path.join(output_folder, f"{output_base_name}_{batch_idx + 1}.png")

        fig.savefig(
            output_path,
            dpi=2000,
            format="png",
            bbox_inches="tight"
        )

        plt.close(fig)
        print(f"4×2 composite figure saved (batch {batch_idx + 1}/{n_batches}, {len(images)} panels):")
        print(output_path)