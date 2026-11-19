"""
Figure for the warm-up: how the first days of a run differ from the later days.

Every run starts with free initial inventory, nothing in transit and no orders waiting, so the first days do not
look like the rest of the run. The pilot (``pilot/run_pilot.py``) records every one of the first 120 days of 30
runs for each case, with the trial settings at several scales. This script draws those records for one scale, one
column for each case: no disruptions of the bakery, and one disruption per 200, 100 or 50 days on average.

The top row shows the network profit made each day. The bottom row shows the inventory level of each tier at the
end of each day. A tier is one level of the supply chain, here the bakery, the 2 distributors, or the 5 shops.
Each line is the mean over the 30 runs of a 7-day moving average, and the band is its 95% confidence interval.
The profit axis stops at ``PROFIT_LIMITS`` so that the later days can be compared. The first days lie above it
and are marked in the figure, and the inventory level below shows them in full. In the first 6 days the moving
average uses the days there are, so the first value is the raw first day. The grey area is the warm-up, whose
statistics the study discards.

The settings are the trial settings of ``model/check_model.py``, not a result of the study.

Run it from the repository folder, after ``pilot/run_pilot.py`` has written ``pilot/results/warm_up.csv``:

    python -m pilot.plot_warm_up

It writes ``pilot/results/warm_up.png``.

Functions:
    read_series: Read the daily records of one scale into lists by case, measure and seed.
    moving_average: Trailing moving average of a list of daily values.
    mean_and_band: Mean over the runs and the half-width of its 95% confidence interval, day by day.
    main: Draw the figure.
"""

import csv
import os
import statistics

import matplotlib

matplotlib.use("Agg")  # draw to a file, no window needed
import matplotlib.pyplot as plt

from model import bread_model as bm
from pilot.run_pilot import OUTPUT_FOLDER, half_width

SCALE = 1.0          # factor on the trial settings (the pilot also has 0.5, 1.1 and 2.0)
WINDOW = 7           # days in the moving average
CASES = [("none", "No disruptions"), ("200", "One disruption per 200 days"),
         ("100", "One disruption per 100 days"), ("50", "One disruption per 50 days")]
# Inventory level of a tier: the sum over its sites, as written by the pilot.
TIERS = [("bakery", "Bakery"), ("distributors", "Distributors"), ("shops", "Shops")]
TIER_COLORS = {"bakery": "#2a78d6", "distributors": "#eb6834", "shops": "#1baf7a"}  # blue, orange, aqua
PROFIT_LIMITS = (-150, 700)  # rupees a day. The first days, with free initial inventory, lie above this
PROFIT_COLOR = "#0b0b0b"
INK = "#52514e"      # axes, labels
GRID = "#e4e3df"
WARM_UP_SHADE = "#efeeea"


def read_series(file_path, scale):
    """
    Read the daily records of one scale.

    Parameters:
        file_path (str): Path of ``warm_up.csv``.
        scale (float): Factor on the trial settings to keep.

    Returns:
        dict: ``series[case][measure][seed]`` is the list of that measure for days 1, 2, ... in order. The
            measures are ``profit`` and ``inventory_level_<tier>``.
    """
    measures = ["profit"] + [f"inventory_level_{tier}" for tier, _ in TIERS]
    series = {}
    with open(file_path, newline="") as file:
        for row in csv.DictReader(file):
            if float(row["scale"]) != scale:
                continue
            by_seed = series.setdefault(row["case"], {m: {} for m in measures})
            for measure in measures:
                by_seed[measure].setdefault(int(row["seed"]), []).append(float(row[measure]))  # file is in day order
    return series


def moving_average(values, window):
    """
    Trailing moving average of a list of daily values.

    Parameters:
        values (list): Values for days 1, 2, ... in order.
        window (int): Number of days to average.

    Returns:
        list: For each day, the mean of that day and the ``window - 1`` days before it (fewer at the start).
    """
    return [statistics.mean(values[max(0, day - window + 1):day + 1]) for day in range(len(values))]


def mean_and_band(by_seed, window):
    """
    Mean over the runs of the moving average, and the half-width of its 95% confidence interval.

    Parameters:
        by_seed (dict): The list of daily values of each seed.
        window (int): Days in the moving average.

    Returns:
        tuple: (means, half_widths), two lists with one value per day.
    """
    smoothed = [moving_average(values, window) for values in by_seed.values()]
    days = len(smoothed[0])
    means = [statistics.mean(run[day] for run in smoothed) for day in range(days)]
    half_widths = [half_width([run[day] for run in smoothed]) for day in range(days)]
    return means, half_widths


def main():
    """
    Draw the figure and write it to ``pilot/results/warm_up.png``.

    Parameters:
        None

    Returns:
        None
    """
    series = read_series(os.path.join(OUTPUT_FOLDER, "warm_up.csv"), SCALE)
    fig, axes = plt.subplots(2, len(CASES), figsize=(14, 6.4), sharex=True, sharey="row")
    n_runs = len(series[CASES[0][0]]["profit"])
    above = []  # (last day above the axis, highest value) of each case

    for column, (case, title) in enumerate(CASES):
        profit_axis, level_axis = axes[0][column], axes[1][column]
        means, bands = mean_and_band(series[case]["profit"], WINDOW)
        days = list(range(1, len(means) + 1))
        above.append((max(day for day, m in zip(days, means) if m > PROFIT_LIMITS[1]), max(means)))
        profit_axis.plot(days, means, color=PROFIT_COLOR, linewidth=1.6)
        profit_axis.fill_between(days, [m - b for m, b in zip(means, bands)], [m + b for m, b in zip(means, bands)],
                                 color=PROFIT_COLOR, alpha=0.15, linewidth=0)
        profit_axis.set_title(title, fontsize=10.5, color=INK, loc="left")

        for tier, label in TIERS:
            means, bands = mean_and_band(series[case][f"inventory_level_{tier}"], WINDOW)
            level_axis.plot(days, means, color=TIER_COLORS[tier], linewidth=1.6, label=label)
            level_axis.fill_between(days, [m - b for m, b in zip(means, bands)], [m + b for m, b in zip(means, bands)],
                                    color=TIER_COLORS[tier], alpha=0.15, linewidth=0)
        level_axis.set_xlabel("Day of the run", color=INK)

        for axis in (profit_axis, level_axis):
            axis.axvspan(0, bm.WARM_UP, color=WARM_UP_SHADE, zorder=0, linewidth=0)
            axis.grid(axis="y", color=GRID, linewidth=0.8)
            axis.set_axisbelow(True)
            axis.set_xlim(0, days[-1])
            axis.tick_params(colors=INK, labelsize=9)
            for side in ("top", "right"):
                axis.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                axis.spines[side].set_color(GRID)

    axes[0][0].set_ylim(*PROFIT_LIMITS)
    axes[0][0].set_ylabel("Network profit a day (rupees)", color=INK)
    axes[1][0].set_ylabel("Inventory level (loaves)", color=INK)
    axes[0][0].text(bm.WARM_UP * 0.65, 0.97, "warm-up", transform=axes[0][0].get_xaxis_transform(), ha="center",
                    va="top", fontsize=9, color=INK)
    last_day, highest = max(day for day, _ in above), max(value for _, value in above)
    axes[0][0].text(bm.WARM_UP + 3, 0.97, f"Days 1-{last_day} are above the axis\n(day 1: {highest:,.0f} a day)",
                    transform=axes[0][0].get_xaxis_transform(), ha="left", va="top", fontsize=9, color=INK)
    axes[1][0].legend(loc="upper right", frameon=False, fontsize=9, labelcolor=INK)
    fig.suptitle(f"Trial values at scale {SCALE}: mean over {n_runs} runs of a {WINDOW}-day moving average, "
                 "with the 95% confidence interval of the mean", fontsize=10.5, color=INK, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(os.path.join(OUTPUT_FOLDER, "warm_up.png"), dpi=200)
    print("Wrote", os.path.join(OUTPUT_FOLDER, "warm_up.png"))


if __name__ == "__main__":
    main()
