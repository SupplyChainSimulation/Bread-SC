"""
Pilot runs of the bread supply chain model: run time, warm-up, run length and the number of replications.

The pilot answers three questions before the optimization starts:

1. How long does one run take, alone and with several runs in parallel?
2. How long must the warm-up be? Every run starts with free initial inventory, nothing in transit and no
   orders waiting, so the first days do not look like the rest of the run.
3. With 10 replications, how wide is the confidence interval of the mean profit, and of the difference in
   profit between two settings run with the same seeds?

The pilot uses the trial settings of ``model/check_model.py`` at several scales. They are not a result of
the study. Seeds 9001 to 9030 are used only by the pilot. Questions 2 and 3 are answered for each case of the
study: no disruptions of the bakery, and one disruption per 200, 100 or 50 days on average. Run time is
measured with no disruptions, and alone also with one disruption per 50 days.

Run it from the repository folder:

    python -m pilot.run_pilot

It writes three CSV files to ``pilot/results/`` and prints a summary.

Functions:
    half_width: Half-width of a 95% confidence interval of a mean.
    timed_run: Time one run.
    daily_series: Run one replication a day at a time and record each day.
    checkpoint_run: Run one replication and record the results at several run lengths.
    write_csv: Write rows to a CSV file.
    part_run_time, part_warm_up, part_replications: The three parts of the pilot.
    main: Run the three parts of the pilot and print the summary.
"""

import csv
import os
import statistics
import time
from multiprocessing import Pool

import SupplyNetPy.Components as scm

from model import bread_model as bm
from model.check_model import trial_settings

SEEDS = list(range(9001, 9031))  # 30 seeds, used only by the pilot
# The cases: mean days between disruptions of the bakery, None for none. "none" in the CSV files.
CASES = [None] + bm.DAYS_BETWEEN_DISRUPTIONS
SCALES = [0.5, 1.0, 1.1, 2.0]    # factors on the trial settings, where 1.0 and 1.1 are close, for a paired comparison
WARM_UP_DAYS = 120               # days recorded one at a time for the warm-up
RUN_LENGTHS = [182, 365, 730]    # days measured after the warm-up
TIMED_RUNS = 96                  # runs timed for each number of workers, enough for several rounds even at 16
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")  # pilot/results/

# Upper 2.5% point of Student's t distribution, by degrees of freedom, for 95% confidence intervals.
T_975 = {9: 2.262, 29: 2.045}

TIERS = {"bakery": ["bakery"], "distributors": ["distributor1", "distributor2"], "shops": bm.SHOPS}


def half_width(values):
    """
    Half-width of the 95% confidence interval of the mean of the values.

    Parameters:
        values (list): Results of independent replications (10 or 30 of them).

    Returns:
        float: t times the standard deviation divided by the square root of the number of values.
    """
    n = len(values)
    return T_975[n - 1] * statistics.stdev(values) / n ** 0.5


def case_name(days_between_disruptions):
    """
    The name of a case in the CSV files and the summary.

    Parameters:
        days_between_disruptions (float): Mean days between disruptions of the bakery, or None for none.

    Returns:
        str: "none", or the mean days between disruptions, for example "50".
    """
    return "none" if days_between_disruptions is None else str(days_between_disruptions)


def timed_run(scale, days_between_disruptions=None):
    """
    Time one run with the warm-up and run length of ``model/bread_model.py``.

    Parameters:
        scale (float): Factor on the trial settings.
        days_between_disruptions (float): Mean days between disruptions of the bakery, or None for none.

    Returns:
        float: Seconds the run took.
    """
    start = time.perf_counter()
    bm.run_network(trial_settings(scale), seed=SEEDS[0], days_between_disruptions=days_between_disruptions)
    return time.perf_counter() - start


def daily_series(args):
    """
    Run one replication from time 0, a day at a time, with no warm-up, and record each day. Running a day at
    a time gives the same results as one long run.

    Parameters:
        args (tuple): (days_between_disruptions, scale, seed).

    Returns:
        list: One dict per day, with the network profit made that day, the expired units of that day and the
            inventory level of each tier at the end of the day.
    """
    days_between_disruptions, scale, seed = args
    sc = bm.build_network(trial_settings(scale), seed, days_between_disruptions)
    rows = []
    profit_before, expired_before = 0.0, 0
    for day in range(1, WARM_UP_DAYS + 1):
        scm.simulate_sc_net(sc, sim_time=day, logging=False)
        row = {"case": case_name(days_between_disruptions), "scale": scale, "seed": seed, "day": day,
               "profit": sc["profit"] - profit_before,
               "expired_units": sc["inventory_waste"] - expired_before}
        for tier, site_ids in TIERS.items():
            row[f"inventory_level_{tier}"] = sum(sc["nodes"][site_id].inventory.level for site_id in site_ids)
        rows.append(row)
        profit_before, expired_before = sc["profit"], sc["inventory_waste"]
    return rows


def checkpoint_run(args):
    """
    Run one replication with the warm-up of ``model/bread_model.py``, and record the results after each run length
    in ``RUN_LENGTHS``. Statistics are reset after the warm-up, so each result covers the measured days only.

    Parameters:
        args (tuple): (days_between_disruptions, scale, seed).

    Returns:
        list: One dict per run length, with the network profit, the profit per year, the customer fill rate of
            the network and the expired units.
    """
    days_between_disruptions, scale, seed = args
    sc = bm.build_network(trial_settings(scale), seed, days_between_disruptions)
    scm.simulate_sc_net(sc, sim_time=bm.WARM_UP, logging=False)
    scm.reset_stats(sc)
    rows = []
    for run_length in RUN_LENGTHS:
        scm.simulate_sc_net(sc, sim_time=bm.WARM_UP + run_length, logging=False)
        ordered = sum(sc["demands"][f"customers_{shop}"].stats.demand_placed[1] for shop in bm.SHOPS)
        delivered = sum(sc["demands"][f"customers_{shop}"].stats.fulfillment_received[1] for shop in bm.SHOPS)
        rows.append({"case": case_name(days_between_disruptions), "scale": scale, "seed": seed,
                     "run_length": run_length, "profit": sc["profit"],
                     "profit_per_year": sc["profit"] * 365 / run_length,
                     "fill_rate": delivered / ordered, "expired_units": sc["inventory_waste"]})
    return rows


def write_csv(rows, file_name):
    """
    Write a list of dicts to a CSV file in the output folder.

    Parameters:
        rows (list): Dicts with the same keys.
        file_name (str): Name of the file.

    Returns:
        None
    """
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    with open(os.path.join(OUTPUT_FOLDER, file_name), "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def part_run_time():
    """
    Part 1: time runs alone, then the throughput with 1 to ``os.cpu_count()`` runs in parallel.

    Parameters:
        None

    Returns:
        list: One dict per measurement.
    """
    print("Part 1: run time (warm-up {} days + {} days measured)".format(bm.WARM_UP, bm.RUN_LENGTH))
    rows = []
    timed_run(1.0)  # the first run in a process also pays for imports and caches
    for days, scale in [(None, scale) for scale in SCALES] + [(min(bm.DAYS_BETWEEN_DISRUPTIONS), 1.0)]:
        times = [timed_run(scale, days) for _ in range(5)]
        rows.append({"measure": "alone", "case": case_name(days), "scale": scale, "workers": 1, "runs": 5,
                     "seconds_per_run": statistics.mean(times)})
        print(f"  alone, case {case_name(days)}, scale {scale}: {statistics.mean(times):.3f} s per run")
    for workers in range(1, os.cpu_count() + 1):
        with Pool(processes=workers) as pool:
            # chunksize=1 hands out one run at a time, so every worker stays busy to the end.
            pool.map(timed_run, [1.0] * workers, chunksize=1)  # start every worker before timing
            start = time.perf_counter()
            pool.map(timed_run, [1.0] * TIMED_RUNS, chunksize=1)
            elapsed = time.perf_counter() - start
        rows.append({"measure": "parallel", "case": "none", "scale": 1.0, "workers": workers, "runs": TIMED_RUNS,
                     "seconds_per_run": elapsed / TIMED_RUNS})
        print(f"  {workers} in parallel: {elapsed / TIMED_RUNS:.3f} s per run in all")
    return rows


def part_warm_up(pool):
    """
    Part 2: the warm-up. Records every day of the first ``WARM_UP_DAYS`` days for each case, scale and seed.
    For each period it prints the daily means over the seeds and, for the profit, the difference from the
    last 60 days, seed by seed, with its 95% confidence interval. A period whose interval holds 0 cannot be
    told apart from the late days.

    Parameters:
        pool (multiprocessing.Pool): Pool for the runs.

    Returns:
        list: One dict per case, scale, seed and day.
    """
    print(f"\nPart 2: warm-up, daily means over {len(SEEDS)} seeds, from time 0 with no reset")
    runs = [(days, scale, seed) for days in CASES for scale in SCALES for seed in SEEDS]
    days_of_run = dict(zip(runs, pool.map(daily_series, runs, chunksize=1)))  # the days of each run, day 1 first
    periods = [(1, 7), (8, 14), (15, 21), (22, 30), (31, 60)]
    late = (WARM_UP_DAYS - 59, WARM_UP_DAYS)
    levels = [f"inventory_level_{tier}" for tier in TIERS]

    def period_mean(days, scale, seed, first, last, measure):
        return statistics.mean(row[measure] for row in days_of_run[(days, scale, seed)][first - 1:last])

    for days in CASES:
        for scale in SCALES:
            print(f"  case {case_name(days)}, scale {scale}")
            print(f"    {'days':<8}{'profit':>9}{'minus late days':>20}{'expired units':>15}"
                  + "".join(f"{'level ' + tier:>20}" for tier in TIERS))
            for first, last in periods + [late]:
                means = {m: statistics.mean(period_mean(days, scale, seed, first, last, m) for seed in SEEDS)
                         for m in ["profit", "expired_units"] + levels}
                if (first, last) == late:
                    difference = ""
                else:
                    diffs = [period_mean(days, scale, seed, first, last, "profit")
                             - period_mean(days, scale, seed, *late, "profit") for seed in SEEDS]
                    difference = f"{statistics.mean(diffs):.0f} +- {half_width(diffs):.0f}"
                print(f"    {f'{first}-{last}':<8}{means['profit']:>9.0f}{difference:>20}"
                      f"{means['expired_units']:>15.1f}" + "".join(f"{means[m]:>20.1f}" for m in levels))
    return [row for run in runs for row in days_of_run[run]]


def part_replications(pool):
    """
    Part 3: run length and replications. For each case, prints the mean profit per year and its 95%
    confidence interval with the first 10 seeds and with all 30, for each run length, and the same for
    paired differences.

    Parameters:
        pool (multiprocessing.Pool): Pool for the runs.

    Returns:
        list: One dict per case, scale, seed and run length.
    """
    print(f"\nPart 3: profit per year, warm-up {bm.WARM_UP} days, 95% confidence intervals")
    runs = [(days, scale, seed) for days in CASES for scale in SCALES for seed in SEEDS]
    rows = [row for result in pool.map(checkpoint_run, runs, chunksize=1) for row in result]

    def values(days, scale, run_length, n):
        by_seed = {row["seed"]: row for row in rows if row["case"] == case_name(days) and row["scale"] == scale
                   and row["run_length"] == run_length}
        return [by_seed[seed] for seed in SEEDS[:n]]

    for days in CASES:
        print(f"  case {case_name(days)}")
        for run_length in RUN_LENGTHS:
            print(f"    run length {run_length} days")
            for scale in SCALES:
                line = f"      scale {scale:<4}"
                for n in (10, 30):
                    profits = [row["profit_per_year"] for row in values(days, scale, run_length, n)]
                    mean, hw = statistics.mean(profits), half_width(profits)
                    line += f"  {n} seeds: {mean:>9.0f} +- {hw:>6.0f} ({100 * hw / abs(mean):.1f}%)"
                fill = statistics.mean(row["fill_rate"] for row in values(days, scale, run_length, 30))
                print(line + f"  fill rate {fill:.3f}")
            for a, b in [(1.1, 1.0), (2.0, 1.0), (0.5, 1.0)]:
                line = f"      {a} minus {b}"
                for n in (10, 30):
                    diffs = [x["profit_per_year"] - y["profit_per_year"]
                             for x, y in zip(values(days, a, run_length, n), values(days, b, run_length, n))]
                    line += f"  {n} seeds: {statistics.mean(diffs):>9.0f} +- {half_width(diffs):>6.0f}"
                print(line)
    return rows


def main():
    """
    Run the three parts of the pilot, write the CSV files and print the summary. Parts 2 and 3 use one
    worker process for each logical processor.

    Parameters:
        None

    Returns:
        None
    """
    write_csv(part_run_time(), "run_time.csv")
    with Pool(processes=os.cpu_count()) as pool:
        write_csv(part_warm_up(pool), "warm_up.csv")
        write_csv(part_replications(pool), "replications.csv")


if __name__ == "__main__":
    main()
