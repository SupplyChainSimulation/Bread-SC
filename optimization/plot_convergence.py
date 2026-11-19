"""
Figure of the convergence of the GA: the best found mean profit so far against the number of model runs so far.

One panel for each case (no disruptions of the bakery, and one disruption per 200, 100 or 50 days on average),
with one line for each of the 5 GA seeds. The x-axis counts calls to the simulation model, that is, runs of the
model so far: the distinct valid candidates run so far times the 10 search seeds. A candidate seen before reuses
its score and a candidate that is not valid is not run, so neither adds runs. The y-axis is the best mean profit
a day on the search seeds so far, one point per generation. A filled dot marks the generation a GA seed stopped
in by the stall rule (no gain for 20 generations), an open dot one that stopped at the cap of 150 generations.
The x-axis is shared by the panels, so the lengths of the runs can be compared.

The starting candidates lose money (several hundred rupees a day), so the y-axis starts at ``PROFIT_LOWEST`` and
the first generations of each line lie below it.

Run it from the repository folder, after the searches of the 4 cases:

    python -m optimization.plot_convergence

It writes ``optimization/results/convergence.png``.

Functions:
    read_climb: Runs of the model and best profit so far, generation by generation, from one search file.
    main: Draw the figure.
"""

import csv
import os

import matplotlib

matplotlib.use("Agg")  # draw to a file, no window needed
import matplotlib.pyplot as plt

from optimization import candidates as cd
from optimization.run_ga import GENERATIONS

GA_SEEDS = [1, 2, 3, 4, 5]
CASE_TITLES = {"none": "No disruptions", "200": "One disruption per 200 days",
               "100": "One disruption per 100 days", "50": "One disruption per 50 days"}
SEED_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # blue, orange, aqua, yellow, magenta
PROFIT_LOWEST = 300  # rupees a day, the lower end of the y-axis
INK = "#52514e"      # axes, labels
GRID = "#e4e3df"


def read_climb(path):
    """
    The runs of the model so far and the best mean profit so far, at the end of each generation.

    Parameters:
        path (str): Path of a ``ga_seed_N.csv`` file of the search.

    Returns:
        tuple: (runs, best), two lists with one value per generation in order. ``runs`` is the number of
            distinct valid candidates run up to and including the generation, times the number of search seeds.
            ``best`` is the highest mean profit a day on the search seeds up to and including the generation.
    """
    seen = set()
    best_so_far = None
    by_generation = {}  # generation: (runs, best)
    with open(path, newline="") as file:
        for row in csv.DictReader(file):  # the file is in generation order
            if row["valid"] == "True":
                seen.add(tuple(int(row[name]) for name in cd.GENE_NAMES))
                per_day = float(row["mean_profit_per_day"])
                if best_so_far is None or per_day > best_so_far:
                    best_so_far = per_day
            by_generation[int(row["generation"])] = (len(seen) * len(cd.SEARCH_SEEDS), best_so_far)
    generations = sorted(by_generation)
    return [by_generation[g][0] for g in generations], [by_generation[g][1] for g in generations]


def main():
    """
    Draw the figure and write it to ``optimization/results/convergence.png``.

    Parameters:
        None

    Returns:
        None
    """
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.4), sharex=True, sharey=True)
    highest = PROFIT_LOWEST
    for axis, case in zip(axes.flat, CASE_TITLES):
        for ga_seed, color in zip(GA_SEEDS, SEED_COLORS):
            runs, best = read_climb(os.path.join(cd.case_folder(case), "search", f"ga_seed_{ga_seed}.csv"))
            highest = max(highest, best[-1])
            axis.plot(runs, best, color=color, linewidth=1.6, label=f"GA seed {ga_seed}")
            at_cap = len(runs) == GENERATIONS  # generations are counted from 0, so the cap is the 150th
            axis.plot(runs[-1], best[-1], "o", markersize=6.5, zorder=3, markeredgewidth=1.6,
                      color="white" if at_cap else color, markeredgecolor=color if at_cap else "white")
        axis.set_title(CASE_TITLES[case], fontsize=10.5, color=INK, loc="left")
        axis.grid(color=GRID, linewidth=0.8)
        axis.set_axisbelow(True)
        axis.tick_params(colors=INK, labelsize=9)
        axis.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            axis.spines[side].set_color(GRID)

    axes[0][0].set_ylim(PROFIT_LOWEST, highest + 20)
    axes[0][0].set_xlim(left=0)
    for axis in axes[:, 0]:
        axis.set_ylabel("Best mean profit so far (rupees a day)", color=INK)
    for axis in axes[1, :]:
        axis.set_xlabel("Runs of the model so far", color=INK)
    axes[0][0].legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
    fig.suptitle("Best mean profit on the 10 search seeds so far, one point per generation. A filled dot marks a GA "
                 "seed stopped by the stall rule (no gain\n"
                 "for 20 generations), an open dot one stopped at the cap of "
                 f"{GENERATIONS} generations. Values below {PROFIT_LOWEST} a day are not shown.",
                 fontsize=10, color=INK, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    path = os.path.join(cd.RESULTS_FOLDER, "convergence.png")
    fig.savefig(path, dpi=200)
    print("Wrote", path)


if __name__ == "__main__":
    main()
