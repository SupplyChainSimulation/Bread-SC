"""
Figures of how disruptions of the bakery change the network profit and the expired units under one ordinary setting.

The x-axis is the disruption rate: the mean number of disruptions of the bakery that start per day, 1 / (mean
days between the starts of two disruptions). It is 0 with no disruptions, and 1/200 = 0.005, 1/100 = 0.01 and
1/50 = 0.02 in the three cases with disruptions. Each disruption lasts 2 days.

The line is the baseline setting of ``baseline_check.py`` (reorder points and order-up-to levels set as days of
each site's mean demand, not found by a search), run in the 4 cases on the 10 search seeds, 1001 to 1010. The
large dot of each case is the mean over the 10 seeds, with its 95% confidence interval. The small dots are the
10 seeds. The seeds have the same customers in every case, so the change from the case with no disruptions is
more certain than the intervals of two dots suggest: those paired differences are in ``baseline_summary.csv``.

The first figure shows the network profit a day, the second the expired units a day (loaves that reached the end
of their shelf life at any site, over the 365 measured days, divided by 365).

Run it from the repository folder, after the baseline check:

    python -m optimization.plot_disruptions

It writes ``disruption_profit.png`` and ``disruption_expired_units.png`` to ``optimization/results/`` and prints the
values drawn.

Functions:
    rate: The disruption rate of a case.
    read_runs: The profit a day and the expired units a day of every run of the baseline check.
    draw: Draw one figure.
    main: Draw both figures.
"""

import csv
import os
import statistics

import matplotlib

matplotlib.use("Agg")  # draw to a file, no window needed
import matplotlib.pyplot as plt

from model import bread_model as bm
from optimization import baseline_check as bc
from optimization import candidates as cd

BASELINE_RUNS = os.path.join(bc.OUTPUT_FOLDER, "baseline_runs.csv")
CASE_ORDER = ["none", "200", "100", "50"]
COLOR = "#2a78d6"  # blue, the first categorical color used across the study's figures
INK = "#52514e"  # axes, labels
GRID = "#e4e3df"


def rate(case):
    """
    The disruption rate of a case.

    Parameters:
        case (str): A key of ``candidates.CASES``.

    Returns:
        float: Mean disruptions of the bakery that start per day: 0 for ``none``, else 1 / (mean days between
            disruptions).
    """
    days = cd.CASES[case]
    return 0.0 if days is None else 1 / days


def read_runs(path):
    """
    The profit a day and the expired units a day of every run of the baseline check.

    Parameters:
        path (str): Path of ``baseline_runs.csv``.

    Returns:
        dict: ``runs[case]`` is a dict with lists ``profit_per_day`` and ``expired_per_day``, one value per seed
            in seed order.
    """
    runs = {}
    with open(path, newline="") as file:
        for row in sorted(csv.DictReader(file), key=lambda r: int(r["seed"])):
            case = runs.setdefault(row["case"], {"profit_per_day": [], "expired_per_day": []})
            case["profit_per_day"].append(float(row["profit_per_day"]))
            case["expired_per_day"].append(float(row["expired_units"]) / bm.RUN_LENGTH)
    return runs


def draw(runs, measure, y_label, title, file_name):
    """
    Draw one figure, write it to ``optimization/results/`` and print its values.

    Parameters:
        runs (dict): As returned by ``read_runs``.
        measure (str): ``profit_per_day`` or ``expired_per_day``.
        y_label (str): Label of the y-axis.
        title (str): Title above the figure.
        file_name (str): Name of the PNG file.

    Returns:
        None
    """
    fig, axis = plt.subplots(figsize=(7.5, 4.8))
    rates = [rate(case) for case in CASE_ORDER]
    means = [statistics.mean(runs[case][measure]) for case in CASE_ORDER]
    half_widths = [bc.half_width(runs[case][measure]) for case in CASE_ORDER]
    for r, case in zip(rates, CASE_ORDER):  # the 10 seeds behind each mean
        axis.scatter([r] * len(runs[case][measure]), runs[case][measure], s=14, color=COLOR, alpha=0.3,
                     linewidths=0, zorder=2)
    axis.errorbar(rates, means, yerr=half_widths, color=COLOR, linewidth=1.8, marker="o", markersize=8,
                  markeredgecolor="white", markeredgewidth=1.2, capsize=3, elinewidth=1.2, zorder=3)
    print(title.splitlines()[0])
    print("  " + ", ".join(f"{case} {m:.2f} +/- {h:.2f}" for case, m, h in zip(CASE_ORDER, means, half_widths)))
    axis.set_xticks(rates)
    axis.set_xticklabels(["0\n(no disruptions)"] + [f"{1 / cd.CASES[c]:g}\n(1 per {cd.CASES[c]} days)"
                                                    for c in CASE_ORDER[1:]])
    axis.set_xlim(-0.001, 0.021)
    axis.set_xlabel("Disruption rate of the bakery (disruptions a day)", color=INK)
    axis.set_ylabel(y_label, color=INK)
    axis.set_title(title, fontsize=10, color=INK, loc="left")
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    axis.tick_params(colors=INK, labelsize=9)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(GRID)
    fig.tight_layout()
    path = os.path.join(cd.RESULTS_FOLDER, file_name)
    fig.savefig(path, dpi=200)
    print("Wrote", path)


def main():
    """
    Draw both figures.

    Parameters:
        None

    Returns:
        None
    """
    runs = read_runs(BASELINE_RUNS)
    note = ("baseline values (reorder points set as days of demand), mean and 95% interval over\n"
            "10 seeds (small dots); each disruption lasts 2 days")
    draw(runs, "profit_per_day", "Network profit (rupees a day)",
         f"Network profit against the disruption rate:\n{note}", "disruption_profit.png")
    draw(runs, "expired_per_day", "Expired units (loaves a day)",
         f"Expired units against the disruption rate:\n{note}", "disruption_expired_units.png")


if __name__ == "__main__":
    main()
