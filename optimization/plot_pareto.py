"""
Figure of the trade-off between network profit and customer fill rate: the Pareto front of each case.

The GA maximizes the mean profit only, but every candidate it runs also has a mean customer fill rate on the
search seeds. A candidate is on the Pareto front of a case when no other candidate of that case has both a higher
mean profit and a higher fill rate (at least as high in one and higher in the other). The front shows what a higher
fill rate costs in profit.

Each case's candidates are those of its 5 GA seeds together, valid ones only, each distinct candidate once. The
values are means over the 10 search seeds, so a point on the front is slightly optimistic: the front is made of
the candidates that did best on those seeds. The search sought profit, not fill rate, so the fronts are thin at
high fill rates, where few candidates were run.

The fronts of the 4 cases (no disruptions of the bakery, and one disruption per 200, 100 or 50 days on average) are
drawn in one panel. The y-axis starts at ``PROFIT_LOWEST``; front points below it are counted in the title.

Run it from the repository folder, after the searches of the 4 cases:

    python -m optimization.plot_pareto

It writes ``optimization/results/pareto.png`` and ``optimization/results/pareto_front.csv`` (the points of the
fronts, with the settings).

Functions:
    read_candidates: The distinct valid candidates of one case, with their mean profit and fill rate.
    pareto_front: The candidates on the Pareto front.
    main: Draw the figure and write the front.
"""

import csv
import os

import matplotlib

matplotlib.use("Agg")  # draw to a file, no window needed
import matplotlib.pyplot as plt

from optimization import candidates as cd

GA_SEEDS = [1, 2, 3, 4, 5]
# Case and its line color: one blue, lighter to darker as disruptions become more frequent.
CASES = [("none", "No disruptions", "#86b6ef"), ("200", "One disruption per 200 days", "#3987e5"),
         ("100", "One disruption per 100 days", "#1c5cab"), ("50", "One disruption per 50 days", "#0d366b")]
PROFIT_LOWEST = 200  # rupees a day, the lower end of the y-axis
INK = "#52514e"      # axes, labels
GRID = "#e4e3df"


def read_candidates(case):
    """
    The distinct valid candidates of one case, from the search files of its 5 GA seeds.

    Parameters:
        case (str): A key of ``candidates.CASES``.

    Returns:
        dict: For each candidate's 16 genes (a tuple), a dict with ``profit`` (mean profit a day on the search
            seeds), ``fill_rate`` (mean customer fill rate), ``expired`` (mean expired units over the 365 days)
            and ``ga_seed`` (the first GA seed that ran it).
    """
    found = {}
    for ga_seed in GA_SEEDS:
        with open(os.path.join(cd.case_folder(case), "search", f"ga_seed_{ga_seed}.csv"), newline="") as file:
            for row in csv.DictReader(file):
                if row["valid"] != "True":
                    continue
                genes = tuple(int(row[name]) for name in cd.GENE_NAMES)
                found.setdefault(genes, {"profit": float(row["mean_profit_per_day"]),
                                         "fill_rate": float(row["mean_fill_rate"]),
                                         "expired": float(row["mean_expired_units"]), "ga_seed": ga_seed})
    return found


def pareto_front(found):
    """
    The candidates that no other candidate beats on both profit and fill rate.

    Parameters:
        found (dict): As returned by ``read_candidates``.

    Returns:
        list: (genes, values) pairs on the front, from the highest fill rate to the highest profit.
    """
    # Going down the fill rate, a candidate is on the front if its profit is above that of every candidate with a
    # higher fill rate (and, among equal fill rates, the highest profit comes first).
    ordered = sorted(found.items(), key=lambda item: (-item[1]["fill_rate"], -item[1]["profit"]))
    front, best_profit = [], None
    for genes, values in ordered:
        if best_profit is None or values["profit"] > best_profit:
            front.append((genes, values))
            best_profit = values["profit"]
    return front


def main():
    """
    Draw the figure, write it to ``optimization/results/pareto.png`` and write the points of the fronts to
    ``optimization/results/pareto_front.csv``.

    Parameters:
        None

    Returns:
        None
    """
    fig, axis = plt.subplots(figsize=(8, 5.4))
    rows, cut = [], []
    for case, label, color in CASES:
        found = read_candidates(case)
        front = pareto_front(found)
        print(f"{label}: {len(found):,} distinct valid candidates, {len(front)} on the front")
        fill_rates = [values["fill_rate"] for _, values in front]
        profits = [values["profit"] for _, values in front]
        axis.plot(fill_rates, profits, color=color, linewidth=1.6, marker="o", markersize=5,
                  markeredgecolor="white", markeredgewidth=0.8, label=label)
        below = sum(1 for p in profits if p < PROFIT_LOWEST)
        if below:
            cut.append(f"{below} of case {case}")
        for genes, values in front:
            rows.append({"case": case, **dict(zip(cd.GENE_NAMES, genes)), "ga_seed": values["ga_seed"],
                         "mean_profit_per_day": values["profit"], "mean_fill_rate": values["fill_rate"],
                         "mean_expired_units": values["expired"]})

    axis.set_ylim(bottom=PROFIT_LOWEST)
    axis.set_xlabel("Customer fill rate (mean on the 10 search seeds)", color=INK)
    axis.set_ylabel("Network profit (rupees a day, mean on the 10 search seeds)", color=INK)
    note = f" Front points below {PROFIT_LOWEST} a day not shown: {', '.join(cut)}." if cut else ""
    axis.set_title("Pareto front of profit and fill rate in each case, from all the candidates its 5 GA seeds "
                   f"ran.\n{note.strip()}", fontsize=10, color=INK, loc="left")
    axis.grid(color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    axis.tick_params(colors=INK, labelsize=9)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(GRID)
    axis.legend(loc="lower left", frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    path = os.path.join(cd.RESULTS_FOLDER, "pareto.png")
    fig.savefig(path, dpi=200)
    print("Wrote", path)

    path = os.path.join(cd.RESULTS_FOLDER, "pareto_front.csv")
    with open(path, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("Wrote", path)


if __name__ == "__main__":
    main()
