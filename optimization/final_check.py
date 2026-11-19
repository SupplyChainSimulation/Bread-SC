"""
Final check of the search: the best found settings of each GA seed, run on 100 new seeds.

Each GA seed picked its best candidate out of thousands on the 10 search seeds, so the candidate's mean profit
on those seeds is biased upward: among many candidates with about the same true profit, the one picked is
likely to be one that happened to do well on those seeds. Running the 5 best found settings on seeds the
search never used gives an unbiased estimate of their profit and shows how large the bias was.

For each of the 5 best found settings the final check reports:

(a) its mean profit on the 10 search seeds, read from the case's ``search/ga_seed_<N>.csv`` (no new
    runs).
(b) its mean profit on seeds 2001 to 2100, with a 95% confidence interval, so that (a) - (b) shows the
    upward bias.
(c) its paired difference in profit from the setting with the highest mean in (b), seed by seed on seeds
    2001 to 2100, with a 95% confidence interval. An interval that contains 0 means the two settings tie.

It also reports, from the same runs, the customer fill rate, the expired units and the average inventory
level of each tier. A tier is one level of the supply chain: the bakery, the 2 distributors, or the 5 shops.

Every setting is run on the same 100 seeds, so all of them face the same customers and the same disruptions
(common random numbers), which is what makes the paired differences in (c) narrower than the intervals in (b).

The final check is made for each case of the study on its own (see ``optimization/candidates.py``). Run it
from the repository folder, after the GA seeds of the case have been run:

    python -m optimization.final_check --case 50

It writes two CSV files to the case's ``final_check`` folder (for example
``optimization/results/disruption_per_50_days/final_check/``) and prints a summary. The final check of the
first search (no disruptions, 60 generations) is in ``optimization/results/final_check/``.

Functions:
    half_width: Half-width of a 95% confidence interval of a mean.
    best_of_search: The best found candidate of one GA seed and its mean profit on the search seeds.
    check_run: Run one candidate on one seed and record its performance metrics.
    write_csv: Write rows to a CSV file.
    final_check: Run the final check and write the CSV files.
    main: Read the case and the GA seeds from the command line and run the final check.
"""

import argparse
import csv
import os
import statistics
import time
from multiprocessing import Pool

from model import bread_model as bm
from optimization import candidates as cd

GA_SEEDS = [1, 2, 3, 4, 5]
CHECK_SEEDS = list(range(2001, 2101))  # 100 seeds, used only by the final check
WORKERS = 8  # runs of the model at once, one for each core of the computer the study ran on

# Upper 2.5% point of Student's t distribution with 99 degrees of freedom, for 95% confidence intervals of
# the mean of 100 values.
T_975 = 1.984

TIERS = {"bakery": ["bakery"], "distributors": ["distributor1", "distributor2"], "shops": bm.SHOPS}


def half_width(values):
    """
    Half-width of the 95% confidence interval of the mean of the values.

    Parameters:
        values (list): Results of 100 independent replications, or 100 paired differences.

    Returns:
        float: t times the standard deviation divided by the square root of the number of values.
    """
    if len(values) != len(CHECK_SEEDS):
        raise ValueError(f"expected {len(CHECK_SEEDS)} values, got {len(values)}")
    return T_975 * statistics.stdev(values) / len(values) ** 0.5


def best_of_search(case, ga_seed):
    """
    The best found candidate of one GA seed: the valid candidate with the highest mean profit on the search
    seeds, read from the GA seed's results file.

    Parameters:
        case (str): The case, a key of ``candidates.CASES``.
        ga_seed (int): The GA seed.

    Returns:
        tuple: (the candidate's 16 genes as a list, its mean profit per day on the search seeds)
    """
    path = os.path.join(cd.case_folder(case), "search", f"ga_seed_{ga_seed}.csv")
    best_genes, best_per_day = None, None
    with open(path, newline="") as file:
        for row in csv.DictReader(file):
            if row["valid"] != "True":
                continue
            per_day = float(row["mean_profit_per_day"])
            if best_per_day is None or per_day > best_per_day:
                best_genes = [int(row[name]) for name in cd.GENE_NAMES]
                best_per_day = per_day
    return best_genes, best_per_day


def check_run(args):
    """
    Run one candidate on one seed, with the warm-up and run length of ``model/bread_model.py``, and record
    its performance metrics over the measured period. This is the work given to each worker process.

    Parameters:
        args (tuple): (ga_seed, genes, seed, days_between_disruptions), the GA seed the candidate came from,
            its 16 genes, the seed of the run, and the mean days between disruptions of the bakery (None for
            none).

    Returns:
        dict: One row of ``final_check_runs.csv``.
    """
    ga_seed, genes, seed, days_between_disruptions = args
    sc = bm.run_network(cd.settings_from_genes(genes), seed, days_between_disruptions)
    ordered = sum(sc["demands"][f"customers_{shop}"].stats.demand_placed[1] for shop in bm.SHOPS)
    delivered = sum(sc["demands"][f"customers_{shop}"].stats.fulfillment_received[1] for shop in bm.SHOPS)
    row = {"ga_seed": ga_seed, "seed": seed, "profit": sc["profit"], "profit_per_day": sc["profit"] / bm.RUN_LENGTH,
           "fill_rate": delivered / ordered, "expired_units": sc["inventory_waste"]}
    # The library's average inventory level is time-weighted and covers the measured period only, since the
    # statistics were reset after the warm-up. A tier's value is the sum over its sites.
    for tier, site_ids in TIERS.items():
        row[f"avg_inventory_level_{tier}"] = sum(sc["nodes"][site_id].stats.avg_inventory_level
                                                 for site_id in site_ids)
    return row


def write_csv(rows, folder, file_name):
    """
    Write a list of dicts to a CSV file.

    Parameters:
        rows (list): Dicts with the same keys.
        folder (str): The folder of the file, made if it does not exist.
        file_name (str): Name of the file.

    Returns:
        None
    """
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, file_name), "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def final_check(case, ga_seeds=GA_SEEDS, workers=WORKERS):
    """
    Run the best found settings of each GA seed of one case on the check seeds, in the same case, write
    ``final_check_runs.csv`` and ``final_check_summary.csv``, and print the summary.

    Parameters:
        case (str): The case, a key of ``candidates.CASES``.
        ga_seeds (list): The GA seeds whose best found settings are checked.
        workers (int): Runs of the model at once.

    Returns:
        list: The rows of ``final_check_summary.csv``.
    """
    start = time.perf_counter()
    output_folder = os.path.join(cd.case_folder(case), "final_check")
    best = {ga_seed: best_of_search(case, ga_seed) for ga_seed in ga_seeds}
    print(f"Final check, case {case}: the best found settings of GA seeds {ga_seeds} on {len(CHECK_SEEDS)} "
          f"new seeds, {workers} workers")
    jobs = [(ga_seed, best[ga_seed][0], seed, cd.CASES[case]) for ga_seed in ga_seeds for seed in CHECK_SEEDS]
    with Pool(processes=workers) as pool:
        # chunksize=1 hands out one run at a time, so every worker stays busy to the end.
        runs = pool.map(check_run, jobs, chunksize=1)
    write_csv(runs, output_folder, "final_check_runs.csv")

    # The profit per day of each setting on each check seed, in the order of CHECK_SEEDS, for the pairing.
    profit = {ga_seed: [run["profit_per_day"] for run in runs if run["ga_seed"] == ga_seed] for ga_seed in ga_seeds}
    leader = max(ga_seeds, key=lambda ga_seed: statistics.mean(profit[ga_seed]))

    summary = []
    for ga_seed in ga_seeds:
        genes, search_mean = best[ga_seed]
        own = [run for run in runs if run["ga_seed"] == ga_seed]
        check_mean = statistics.mean(profit[ga_seed])
        differences = [mine - theirs for mine, theirs in zip(profit[ga_seed], profit[leader])]
        row = {"ga_seed": ga_seed}
        row.update(dict(zip(cd.GENE_NAMES, genes)))
        row.update({
            "search_mean_profit_per_day": search_mean,                           # (a)
            "check_mean_profit_per_day": check_mean,                             # (b)
            "check_half_width": half_width(profit[ga_seed]),
            "upward_bias_per_day": search_mean - check_mean,                     # (a) - (b)
            "leader_ga_seed": leader,
            "difference_from_leader_per_day": statistics.mean(differences),      # (c)
            # The leader's differences from itself are all 0, so its half-width is 0 too.
            "difference_half_width": half_width(differences) if ga_seed != leader else 0.0,
            "mean_fill_rate": statistics.mean(run["fill_rate"] for run in own),
            "mean_expired_units": statistics.mean(run["expired_units"] for run in own),
        })
        for tier in TIERS:
            row[f"mean_avg_inventory_level_{tier}"] = statistics.mean(run[f"avg_inventory_level_{tier}"]
                                                                      for run in own)
        summary.append(row)
    write_csv(summary, output_folder, "final_check_summary.csv")

    print(f"{'GA seed':>7} {'(a) search':>11} {'(b) check':>17} {'(a)-(b)':>8} {'(c) vs best':>17} "
          f"{'fill rate':>9} {'expired':>8}")
    for row in summary:
        print(f"{row['ga_seed']:>7} {row['search_mean_profit_per_day']:>11.1f} "
              f"{row['check_mean_profit_per_day']:>9.1f} +/- {row['check_half_width']:<5.1f} "
              f"{row['upward_bias_per_day']:>8.1f} "
              f"{row['difference_from_leader_per_day']:>9.1f} +/- {row['difference_half_width']:<5.1f} "
              f"{row['mean_fill_rate']:>9.3f} {row['mean_expired_units']:>8.0f}")
    print(f"Profit in rupees a day; expired units over the {bm.RUN_LENGTH} measured days. "
          f"(c) is the paired difference from GA seed {leader}, the highest mean in (b).")
    print(f"Done in {(time.perf_counter() - start) / 60:.1f} minutes. Written to {output_folder}")
    return summary


def main():
    """
    Read the case and the GA seeds from the command line and run the final check.

    Parameters:
        None

    Returns:
        None
    """
    parser = argparse.ArgumentParser(description="Run the best found settings of each GA seed on new seeds.")
    parser.add_argument("--case", choices=list(cd.CASES), required=True,
                        help="none for no disruptions, or the mean days between disruptions of the bakery")
    parser.add_argument("--ga-seeds", type=int, nargs="+", default=GA_SEEDS,
                        help="GA seeds whose best found settings are checked (default: 1 to 5)")
    arguments = parser.parse_args()
    final_check(arguments.case, arguments.ga_seeds)


if __name__ == "__main__":
    main()
