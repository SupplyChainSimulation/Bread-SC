"""
Cross-case check: each case's best found settings, run in every case.

The search is made for each case on its own (no disruptions of the bakery, and one disruption per 200, 100 or 50
days on average), so each case has its own best found settings. This check shows what searching with the
disruptions in the model gains. It runs the best found settings of each case in all the cases, on the new seeds
2001 to 2100 of the final check, and reports, for each case in which the settings are run:

- the mean profit a day of each case's settings, with a 95% confidence interval.
- the paired difference, seed by seed, from the settings found for the case being run (their own settings), with
  a 95% confidence interval. A negative difference is what the other case's settings lose against settings
  searched for this case. An interval that contains 0 means the two settings tie.
- the customer fill rate, the expired units and the average inventory level of each tier.

The best found settings of a case are those of the GA seed with the highest mean profit in the case's final check
(``final_check.py``), so run the final check of every case first. Every setting is run on the same seeds, so
all of them face the same customers and the same disruptions (common random numbers), and the differences are
paired.

Run it from the repository folder, after the final checks of the 4 cases:

    python -m optimization.cross_case_check

It writes two CSV files to ``optimization/results/cross_case/`` and prints a summary. It makes 4 x 4 x 100 runs of
the model, about 3 minutes on the computer the study ran on.

Functions:
    leader_settings: The best found settings of one case, from its final check.
    cross_run: Run one case's settings on one seed in one case.
    write_summary_rows: Summarize the runs, one row for each pair of settings and case.
    cross_case_check: Run the check and write the CSV files.
    main: Run the check.
"""

import csv
import os
import statistics
import time
from multiprocessing import Pool

from model import bread_model as bm
from optimization import candidates as cd
from optimization import final_check as fc

OUTPUT_FOLDER = os.path.join(cd.RESULTS_FOLDER, "cross_case")


def leader_settings(case):
    """
    The best found settings of one case: the settings of the GA seed with the highest mean profit on the new
    seeds, read from the case's ``final_check_summary.csv``.

    Parameters:
        case (str): The case, a key of ``candidates.CASES``.

    Returns:
        tuple: (the GA seed, the settings' 16 genes as a list)
    """
    path = os.path.join(cd.case_folder(case), "final_check", "final_check_summary.csv")
    with open(path, newline="") as file:
        rows = list(csv.DictReader(file))
    leader = int(rows[0]["leader_ga_seed"])
    row = next(row for row in rows if int(row["ga_seed"]) == leader)
    return leader, [int(row[name]) for name in cd.GENE_NAMES]


def cross_run(args):
    """
    Run one case's best found settings on one seed, in one case. This is the work given to each worker process.

    Parameters:
        args (tuple): (settings_from_case, genes, evaluated_in_case, seed), the case the settings were found for,
            their 16 genes, the case of the run, and the seed of the run.

    Returns:
        dict: One row of ``cross_case_runs.csv``.
    """
    settings_from_case, genes, evaluated_in_case, seed = args
    row = fc.check_run((settings_from_case, genes, seed, cd.CASES[evaluated_in_case]))
    row.pop("ga_seed")  # check_run labels a run by the GA seed, but here the label is the case
    return {"settings_from_case": settings_from_case, "evaluated_in_case": evaluated_in_case, **row}


def write_summary_rows(runs, cases, leaders):
    """
    Summarize the runs: one row for each case's settings run in each case.

    Parameters:
        runs (list): The rows of ``cross_case_runs.csv``.
        cases (list): The cases, in order.
        leaders (dict): The GA seed of each case's best found settings.

    Returns:
        list: The rows of ``cross_case_summary.csv``.
    """
    # Profit per day of each pair on each seed, in the order of the check seeds, for the pairing.
    selected = {(a, b): [run for run in runs if run["settings_from_case"] == a and run["evaluated_in_case"] == b]
                for a in cases for b in cases}
    summary = []
    for evaluated in cases:
        own = [run["profit_per_day"] for run in selected[(evaluated, evaluated)]]
        for source in cases:
            these = selected[(source, evaluated)]
            profit = [run["profit_per_day"] for run in these]
            differences = [mine - theirs for mine, theirs in zip(profit, own)]
            row = {"evaluated_in_case": evaluated, "settings_from_case": source,
                   "settings_ga_seed": leaders[source],
                   "mean_profit_per_day": statistics.mean(profit),
                   "half_width": fc.half_width(profit),
                   "difference_from_own_per_day": statistics.mean(differences),
                   # The settings' difference from themselves is 0 on every seed, so its half-width is 0 too.
                   "difference_half_width": fc.half_width(differences) if source != evaluated else 0.0,
                   "mean_fill_rate": statistics.mean(run["fill_rate"] for run in these),
                   "mean_expired_units": statistics.mean(run["expired_units"] for run in these)}
            for tier in fc.TIERS:
                row[f"mean_avg_inventory_level_{tier}"] = statistics.mean(
                    run[f"avg_inventory_level_{tier}"] for run in these)
            summary.append(row)
    return summary


def cross_case_check(cases=list(cd.CASES), workers=fc.WORKERS):
    """
    Run the best found settings of each case in every case on the check seeds, write ``cross_case_runs.csv`` and
    ``cross_case_summary.csv``, and print the summary.

    Parameters:
        cases (list): The cases, keys of ``candidates.CASES``.
        workers (int): Runs of the model at once.

    Returns:
        list: The rows of ``cross_case_summary.csv``.
    """
    start = time.perf_counter()
    found = {case: leader_settings(case) for case in cases}
    leaders = {case: found[case][0] for case in cases}
    print(f"Cross-case check: the best found settings of cases {cases} (GA seeds {list(leaders.values())}), "
          f"each run in every case on {len(fc.CHECK_SEEDS)} new seeds, {workers} workers")
    jobs = [(source, found[source][1], evaluated, seed)
            for evaluated in cases for source in cases for seed in fc.CHECK_SEEDS]
    with Pool(processes=workers) as pool:
        # chunksize=1 hands out one run at a time, so every worker stays busy to the end.
        runs = pool.map(cross_run, jobs, chunksize=1)
    fc.write_csv(runs, OUTPUT_FOLDER, "cross_case_runs.csv")
    summary = write_summary_rows(runs, cases, leaders)
    fc.write_csv(summary, OUTPUT_FOLDER, "cross_case_summary.csv")

    print(f"{'run in case':>11} {'settings from':>13} {'profit a day':>17} {'minus own settings':>20} "
          f"{'fill rate':>9} {'expired':>8}")
    for row in summary:
        print(f"{row['evaluated_in_case']:>11} {row['settings_from_case']:>13} "
              f"{row['mean_profit_per_day']:>9.1f} +/- {row['half_width']:<5.1f} "
              f"{row['difference_from_own_per_day']:>11.1f} +/- {row['difference_half_width']:<5.1f} "
              f"{row['mean_fill_rate']:>9.3f} {row['mean_expired_units']:>8.0f}")
    print(f"Profit in rupees a day; expired units over the {bm.RUN_LENGTH} measured days. The difference is "
          "from the settings found for the case being run.")
    print(f"Done in {(time.perf_counter() - start) / 60:.1f} minutes. Written to {OUTPUT_FOLDER}")
    return summary


def main():
    """
    Run the cross-case check for all the cases.

    Parameters:
        None

    Returns:
        None
    """
    cross_case_check()


if __name__ == "__main__":
    main()
