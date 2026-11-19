"""
The search by simulated annealing (SA): it looks for the (s, S) settings of the 8 sites that hold bread that
give the highest mean network profit. The simulation is a black box to SA, which sees only the results of its
runs and not how the model works inside.

Candidates, their scores and the step that changes them are described in ``optimization/candidates.py``.

SA keeps one current candidate, starting from a valid one drawn at random. At each step it changes one gene
of the current candidate by a small random step (the same step as the GA's mutation) and scores the new
candidate. A better new candidate always replaces the current one. A worse one replaces it with probability
exp(-d / T), where d is how much less profit it makes, in rupees a day, and T is the temperature, also in
rupees a day. T falls by the same factor at every step, from ``T_START`` to ``T_END``, so early on SA often
accepts a worse candidate and can leave a poor region, and late on it hardly ever does. A new candidate with s
at or above S at some site is not run and is never accepted. The result is the best candidate seen at any
step, not the last current one. 3,000 steps give 3,000 candidates, the same budget as the GA had in the
first search of the study (no disruptions, a fixed 60 generations).

Each step scores one candidate on the 10 search seeds, so only 10 runs can go at once. With 10 workers, each
step takes about as long as one run.

SA can run from SA seeds 1 to 5, with no disruptions. The study ran SA seed 1 only, as a test, and uses the
GA for its results. Each run is one command, from the repository folder:

    python -m optimization.run_sa --sa-seed 1

It writes ``optimization/results/search/sa_seed_<N>.csv``, one row per step, flushed to disk at every step.
Running an SA seed again starts it from the beginning, overwrites its file and gives the same results,
whatever the number of workers.

Functions:
    temperature: The temperature at a step.
    run_sa: Run SA for one SA seed and write its CSV file.
    main: Read the SA seed from the command line and run SA.
"""

import argparse
import csv
import math
import os
import random
import time
from multiprocessing import Pool

from model import bread_model as bm
from optimization import candidates as cd

STEPS = 3000        # candidates scored, counting the starting one
T_START = 100.0     # rupees a day. At first, a candidate 100 rupees a day worse is accepted with probability 0.37
T_END = 1.0         # rupees a day. At the end, a candidate 1 rupee a day worse is accepted with probability 0.37
WORKERS = 10        # runs of the model at once, one per search seed, so that all the runs of a step go at once
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "search")


def temperature(step, steps):
    """
    The temperature at a step. It falls by the same factor at every step, from ``T_START`` at step 0 to
    ``T_END`` at the last step.

    Parameters:
        step (int): The step, 0 for the starting candidate.
        steps (int): Steps in all.

    Returns:
        float: The temperature, in rupees a day.
    """
    return T_START * (T_END / T_START) ** (step / (steps - 1))


def run_sa(sa_seed, steps=STEPS, seeds=cd.SEARCH_SEEDS, workers=WORKERS, output_folder=OUTPUT_FOLDER):
    """
    Run SA for one SA seed and write ``sa_seed_<N>.csv`` to the output folder. The parameters after the SA
    seed are there for short test runs. The study uses their default values.

    Parameters:
        sa_seed (int): The seed of SA's own random numbers: the starting candidate, the steps and the
            acceptance of worse candidates.
        steps (int): Candidates scored, counting the starting one.
        seeds (list): The search seeds.
        workers (int): Runs of the model at once.
        output_folder (str): Folder for the CSV file.

    Returns:
        tuple: (the best candidate's 16 genes, its mean profit per day)
    """
    rng = random.Random(f"simulated annealing, seed {sa_seed}")
    os.makedirs(output_folder, exist_ok=True)
    path = os.path.join(output_folder, f"sa_seed_{sa_seed}.csv")
    start = time.perf_counter()
    print(f"SA seed {sa_seed}: {steps} steps, {len(seeds)} seeds each, {workers} workers")
    with open(path, "w", newline="") as file, Pool(processes=workers) as pool:
        scorer = cd.Scorer(pool, seeds)
        writer = csv.writer(file)
        writer.writerow(["step", "temperature"] + cd.candidate_columns(seeds)
                        + ["accepted", "current_profit_per_day", "best_profit_per_day"])
        current = cd.random_candidate(rng)
        current_score = scorer.score([current], 0)[0]
        not_valid = 0
        for step in range(steps):
            t = temperature(step, steps)
            if step == 0:
                candidate, score, accepted = current, current_score, True
            else:
                candidate = cd.step(current, rng)
                score = scorer.score([candidate], step)[0]
                if not cd.is_valid(candidate):
                    accepted = False
                    not_valid += 1
                else:
                    worse_by = (current_score - score) / bm.RUN_LENGTH  # rupees a day, 0 or less if not worse
                    accepted = worse_by <= 0 or rng.random() < math.exp(-worse_by / t)
            if accepted:
                current, current_score = candidate, score
            best, best_per_day = scorer.best()
            writer.writerow([step, t] + scorer.describe(candidate)
                            + [accepted, current_score / bm.RUN_LENGTH, best_per_day])
            file.flush()
            os.fsync(file.fileno())
            if step % 100 == 0 or step == steps - 1:
                print(f"  step {step}: temperature {t:.1f}, current {current_score / bm.RUN_LENGTH:.1f}, "
                      f"best so far {best_per_day:.1f} rupees a day, {len(scorer.results)} candidates run, "
                      f"{not_valid} not valid")
    best, best_per_day = scorer.best()
    minutes = (time.perf_counter() - start) / 60
    print(f"Done in {minutes:.1f} minutes. Best found: {best_per_day:.1f} rupees a day, "
          f"{cd.settings_from_genes(best)}")
    print(f"{len(scorer.results)} candidates run ({len(scorer.results) * len(seeds)} runs), "
          f"{not_valid} not valid. Written to {path}")
    return list(best), best_per_day


def main():
    """
    Read the SA seed from the command line and run SA.

    Parameters:
        None

    Returns:
        None
    """
    parser = argparse.ArgumentParser(description="Search the (s, S) settings with simulated annealing.")
    parser.add_argument("--sa-seed", type=int, required=True, help="seed of simulated annealing, 1 to 5 in the study")
    run_sa(parser.parse_args().sa_seed)


if __name__ == "__main__":
    main()
