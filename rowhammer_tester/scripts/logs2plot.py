#!/usr/bin/env python3
"""
This script generates plots from rowhammer attack logs using matplotlib.
Depending on chosen mode, it will generate one or many separate plots.
"""

import os
import argparse
import json

from pathlib import Path
from matplotlib import cm
from matplotlib import colors
from matplotlib import pyplot as plt
import numpy as np

from rowhammer_tester.scripts.utils import get_generated_file


def plot_single_attack(data: dict, _rows: int, cols: int, col_step=32, title=""):
    affected_rows_count = len(data["errors_in_rows"])

    # row_labels correspond to actual row numbers, but row_vals
    # start from 0, to prevent displaying rows between them
    row_labels: list[str] = []
    row_vals: list[int] = []

    # cols_vals are normal column numbers
    col_vals: list[int] = []

    for i, (row, row_errors) in enumerate(data["errors_in_rows"].items()):
        row_labels.append(row)
        for col, col_errors in row_errors["col"].items():
            for _ in col_errors:
                row_vals.append(i)
                col_vals.append(int(col))

    bins = [range(0, cols + 1, col_step), np.arange(min(row_vals) - 0.5, max(row_vals) + 1, 1)]

    # custom cmap with white color for 0
    custom_cmap = colors.ListedColormap(["white", *cm.get_cmap("viridis").colors])

    h, _, _, _ = plt.hist2d(
        col_vals,
        row_vals,
        bins=bins,
        range=[[0, cols // col_step], [min(row_vals), max(row_vals)]],
        cmap=custom_cmap)

    plt.xlabel('Column')
    plt.xticks(range(0, cols + 1, col_step))

    plt.ylabel('Row')
    plt.yticks(range(affected_rows_count), row_labels)

    # limit number of colorbar ticks
    # if left unchanged they can be floats, which looks bad
    max_errors = int(h.max())
    ticks_step = max(1, int(max_errors // 20))
    plt.colorbar(ticks=range(0, max_errors + 1, ticks_step))

    plt.title(title)
    plt.show()


def plot_aggressors_vs_victims(data: dict, annotate: str):
    aggressors: list[int] = []
    victims: list[int] = []
    bitflips: list[int] = []

    # Agressors (a) with victims (v) and bitflips (b) packed into tuple (a, v, b)
    avb_packed: list[tuple(int, int, int)] = []

    # Put aggressors and its victims into lists for hist2d
    for aggressor, victim in data.items():
        # Each victim must have its corresponding aggressor
        for v in victim:
            # From json file - v[1] is a single victim row hierarchy
            bitflip_amount = v[1]["bitflips"]
            row_number = v[1]["row"]

            victims.append(row_number)
            aggressors.append(aggressor)
            bitflips.append(bitflip_amount)

            # Pack data for annotation
            avb_packed.append((aggressors[-1], victims[-1], bitflip_amount))

    min_victim = min(sorted(victims))
    max_victim = max(sorted(victims))
    min_aggressor = min(sorted(aggressors))
    max_aggressor = max(sorted(aggressors))

    bins = [max_victim - min_victim + 1, max_aggressor - min_aggressor + 1]
    hist_range = [[min_victim, max_victim + 1], [min_aggressor, max_aggressor + 1]]

    # Custom color map with white color for 0
    custom_cmap = colors.ListedColormap(["white", *cm.get_cmap("viridis").colors])

    _, ax = plt.subplots()
    h, _, _, qm = ax.hist2d(
        victims,
        aggressors,
        bins=bins,
        range=hist_range,
        weights=bitflips,
        cmap=custom_cmap,
    )

    # Do not annotate by default since it slows down a plot and it makes it hard
    # to read without zooming in
    if annotate == "bitflips":
        for a, v, b in avb_packed:
            ax.text(
                v + 0.5, a + 0.5, f"{b}", color="w", ha="center", va="center", fontweight="bold")

    ax.set_xlabel('Victim')
    ax.set_xticks(range(min_victim, max_victim + 1))

    ax.set_ylabel('Aggressor')
    ax.set_yticks(range(min_aggressor, max_aggressor + 1))

    # Limit number of colorbar ticks
    # if left unchanged they can be floats, which looks bad
    max_errors = int(h.max())
    ticks_step = max(1, int(max_errors // 20))

    ax.grid(visible=True, which="both", color="gray", alpha=0.2, linestyle="-")

    plt.colorbar(qm, ticks=range(0, max_errors + 1, ticks_step))
    plt.title(
        f"Aggressors ({min_aggressor}, {max_aggressor}) vs victims ({min_victim}, {max_victim})")

    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("log_file", help="file with log output")
    parser.add_argument(
        "--plot-columns", type=int, default=32, help="how many columns to show in resulting grid")
    parser.add_argument(
        "--aggressors-vs-victims",
        action="store_true",
        help="Plot agressors against their victims.")
    parser.add_argument(
        "--annotate",
        type=str,
        default="color",
        choices=["color", "bitflips"],
        help="Annotate heat map with number of bitflips or just a color (default: color).")
    # TODO: add option to save plots to files without showing GUI
    args = parser.parse_args()

    settings_file = Path(get_generated_file("litedram_settings.json"))
    with settings_file.open() as fd:
        settings = json.load(fd)

    COLS = 2**settings["geom"]["colbits"]
    ROWS = 2**settings["geom"]["rowbits"]

    log_file = Path(args.log_file)
    with log_file.open() as fd:
        log_data = json.load(fd)

    for _, attack_set_results in log_data.items():
        aggressors_vs_victims = {}
        # Remove read_count as it's only disturbing here
        if "read_count" in attack_set_results:
            attack_set_results.pop("read_count")

        # Single attack hierarchy
        for attack, attack_results in attack_set_results.items():
            if attack.startswith("pair"):
                hammered_rows = (attack_results["hammer_row_1"], attack_results["hammer_row_2"])
                title = f"Hammered rows: {hammered_rows}"
            elif attack.startswith("sequential"):
                start_row = attack_results["row_pairs"][0][1]
                end_row = attack_results["row_pairs"][-1][1]
                title = f"Sequential attack on rows from {start_row} to {end_row}"

                if args.aggressors_vs_victims:
                    print(
                        "ERROR: Sequential attacks are not hammering a single row. Unable to compare aggressors against victims."
                    )
                    exit()

            # Collect all attack data into one dict if we plot aggressors vs victims
            if args.aggressors_vs_victims:
                # We don't need anything but victim rows hierarchy to generate plot
                victim_rows = []
                for row in attack_results["errors_in_rows"].items():
                    victim_rows.append(row)

                hammered_row = hammered_rows[0]
                aggressors_vs_victims[hammered_row] = victim_rows

                if hammered_rows[0] != hammered_rows[1]:
                    print(
                        "ERROR: Attacks are not hammering single rows. Unable to plot aggressors "
                        "against their victims. Use `--row-pair-distance 0` to target single row at once."
                    )
                    exit()
            # Otherwise plot single attack immediately
            else:
                plot_single_attack(
                    attack_results,
                    ROWS,
                    COLS,
                    COLS // args.plot_columns,
                    title=title,
                )
        if args.aggressors_vs_victims:
            plot_aggressors_vs_victims(aggressors_vs_victims, args.annotate)
