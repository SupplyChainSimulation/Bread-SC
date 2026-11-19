"""
Baseline check: how the disruptions of the bakery change the network under one ordinary setting.

The figures of the disruptions' effect need one fixed (s, S) setting that is not the result of a search. A setting
found by the search has been tuned to its case, so the effect of disruptions on it mixes the disruptions with the
tuning. The baseline here is a plain rule: each site's reorder point s and order-up-to level S are set as days of
its own mean demand, the same trial setting that ``model/check_model.py`` uses (scale 1.0):

    bakery        s = 0.5 days,  S = 2.0 days
    distributors  s = 1.0 day,   S = 2.0 days
    shops         s = 0.5 days,  S = 1.5 days

The baseline is run in the 4 cases (no disruptions, and one disruption of the bakery per 200, 100 and 50 days on
average) on the 10 search seeds, 1001 to 1010. The baseline is not chosen by a search, so these seeds do not
favor it. Every case uses the same seeds, so a seed has the same customers in every case and the differences from
the case with no disruptions are paired.

Run it from the repository folder:

    python -m optimization.baseline_check

It writes ``baseline_runs.csv`` (one row for each case and seed) and ``baseline_summary.csv`` (one row for each
case) to ``optimization/results/baseline/`` and prints the summary. It makes 4 x 10 runs of the model.

Functions:
    baseline_genes: The 16 genes of the baseline setting.
    summarize: Summarize the runs, one row for each case.
    main: Run the check.
"""

import os
import statistics
import time
from multiprocessing import Pool

from model import bread_model as bm
from model.check_model import trial_settings
from optimization import candidates as cd
from optimization import final_check as fc

SEEDS = cd.SEARCH_SEEDS  # 1001 to 1010
T_975 = 2.262  # 97.5th percentile of Student's t with 9 degrees of freedom (10 seeds)
OUTPUT_FOLDER = os.path.join(cd.RESULTS_FOLDER, "baseline")
LABEL = "baseline"


def baseline_genes():
    """
    The 16 genes of the baseline setting, in the order of ``candidates.SITE_IDS``.

    Parameters:
        None

    Returns:
        list: s and S of each site, from the trial setting of the model checks at scale 1.0.
    """
    settings = trial_settings(1.0)
    genes = []
    for site_id in cd.SITE_IDS:
        genes += [settings[site_id]["s"], settings[site_id]["S"]]
    return genes


def half_width(values):
    """
    Half-width of the 95% confidence interval of the mean of 10 values.

    Parameters:
        values (list): Results of the 10 seeds, or 10 paired differences.

    Returns:
        float: t times the standard deviation divided by the square root of 10.
    """
    if len(values) != len(SEEDS):
        raise ValueError(f"expected {len(SEEDS)} values, got {len(values)}")
    return T_975 * statistics.stdev(values) / len(values) ** 0.5


def summarize(runs, cases):
    """
    Summarize the runs, one row for each case.

    Parameters:
        runs (list): The rows of ``baseline_runs.csv``.
        cases (list): The cases, in order. The first must be the case with no disruptions.

    Returns:
        list: The rows of ``baseline_summary.csv``. Profit and expired units are a day, over the measured days.
            The difference is from the case with no disruptions, seed by seed, with its 95% half-width.
    """
    by_case = {case: sorted((r for r in runs if r["case"] == case), key=lambda r: r["seed"]) for case in cases}
    reference = [r["profit_per_day"] for r in by_case[cases[0]]]
    summary = []
    for case in cases:
        profit = [r["profit_per_day"] for r in by_case[case]]
        expired = [r["expired_units"] / bm.RUN_LENGTH for r in by_case[case]]
        differences = [mine - base for mine, base in zip(profit, reference)]
        summary.append({"case": case,
                        "mean_profit_per_day": statistics.mean(profit), "profit_half_width": half_width(profit),
                        "difference_from_none_per_day": statistics.mean(differences),
                        "difference_half_width": half_width(differences),
                        "mean_expired_units_per_day": statistics.mean(expired),
                        "expired_half_width": half_width(expired),
                        "mean_fill_rate": statistics.mean(r["fill_rate"] for r in by_case[case])})
    return summary


def main():
    """
    Run the baseline in every case on the 10 search seeds, write the two CSV files and print the summary.

    Parameters:
        None

    Returns:
        None
    """
    start = time.perf_counter()
    genes = baseline_genes()
    cases = list(cd.CASES)
    print("Baseline setting:", dict(zip(cd.GENE_NAMES, genes)))
    jobs = [(LABEL, genes, seed, cd.CASES[case]) for case in cases for seed in SEEDS]
    job_cases = [case for case in cases for _ in SEEDS]  # the case of each job, in the same order
    with Pool(processes=fc.WORKERS) as pool:
        rows = pool.map(fc.check_run, jobs, chunksize=1)
    runs = []
    for case, row in zip(job_cases, rows):
        row.pop("ga_seed")  # check_run labels a run by the GA seed, but here the label is the case
        runs.append({"case": case, **row})
    fc.write_csv(runs, OUTPUT_FOLDER, "baseline_runs.csv")
    summary = summarize(runs, cases)
    fc.write_csv(summary, OUTPUT_FOLDER, "baseline_summary.csv")

    print(f"{'case':>6} {'profit a day':>18} {'minus no disruptions':>24} {'expired a day':>16} {'fill rate':>9}")
    for row in summary:
        print(f"{row['case']:>6} {row['mean_profit_per_day']:>9.1f} +/- {row['profit_half_width']:<5.1f} "
              f"{row['difference_from_none_per_day']:>11.1f} +/- {row['difference_half_width']:<5.1f} "
              f"{row['mean_expired_units_per_day']:>8.2f} +/- {row['expired_half_width']:<4.2f} "
              f"{row['mean_fill_rate']:>9.3f}")
    print(f"Seeds {SEEDS[0]}-{SEEDS[-1]}, 95% half-widths. Done in {(time.perf_counter() - start) / 60:.1f} "
          f"minutes. Written to {OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()
