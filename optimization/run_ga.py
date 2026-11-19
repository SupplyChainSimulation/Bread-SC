"""
The search by a genetic algorithm (GA): it looks for the (s, S) settings of the 8 sites that hold bread that
give the highest mean network profit. The simulation is a black box to the GA, which sees only the results
of its runs and not how the model works inside.

Candidates, their scores and the step that changes them are described in ``optimization/candidates.py``.

The GA is PyGAD's. It starts from 50 valid candidates drawn at random. Each generation keeps the best candidate
unchanged and replaces the other 49 with children. A child takes the genes of one parent up to a random point
and the rest from another (single-point crossover), and then one of its genes moves by a small random step
(mutation). The parents are the 25 candidates with the highest scores. A child with s at or above S at some
site is not run, and gets a score far below any profit, so it is never picked as a parent.

The GA stops when the best candidate has not improved for 20 generations (the stall rule), or after 150
generations (the starting one and 149 more), whichever comes first.

The study searches 4 cases, each on its own: no disruptions of the bakery (``none``), and one disruption per
200, 100 or 50 days on average (``200``, ``100``, ``50``). In each case it runs the GA 5 times, each started
from its own GA seed (1 to 5). Each run is one command, from the repository folder:

    python -m optimization.run_ga --case 50 --ga-seed 1

It writes ``ga_seed_<N>.csv`` to the case's ``search`` folder (for example
``optimization/results/disruption_per_50_days/search/``), one row per candidate in each generation, and adds
the rows of each generation as soon as it is scored, so a crash loses at most one generation. Running a GA seed
again starts it from the beginning, overwrites its file and gives the same results. The results do not depend
on the number of workers: all random numbers of the GA are drawn in the main process, and each run of the
model is fixed by its settings and seed.

The first search of the study (no disruptions, a fixed 60 generations and no stall rule) is in
``optimization/results/search/``.

Functions:
    step_mutation: PyGAD's mutation step: one step for each child.
    run_ga: Run the GA for one case and GA seed and write its CSV file.
    main: Read the case and the GA seed from the command line and run the GA.
"""

import argparse
import csv
import os
import random
import time
from multiprocessing import Pool

import pygad

from model import bread_model as bm
from optimization import candidates as cd

POPULATION = 50     # candidates in each generation
GENERATIONS = 150   # the most generations, counting the starting one, so at most 50 x 150 = 7,500 candidates
STALL = 20          # stop when the best candidate has not improved for this many generations
PARENTS = 25        # the candidates with the highest scores in a generation, the best half, mate
KEEP_ELITISM = 1    # the best candidate passes to the next generation unchanged
WORKERS = 8         # runs of the model at once, one per core of the computer used


def step_mutation(children, ga):
    """
    PyGAD's mutation step. Each child gets one step (``candidates.step``): one gene moves by a small random
    amount. The step draws from PyGAD's own random number generator, which the GA seed starts.

    Parameters:
        children (numpy.ndarray): The children made by crossover, one row each.
        ga (pygad.GA): The GA.

    Returns:
        numpy.ndarray: The mutated children.
    """
    children = children.copy()
    for i in range(len(children)):
        children[i] = cd.step(children[i], ga.python_random_generator)
    return children


def run_ga(case, ga_seed, population=POPULATION, generations=GENERATIONS, stall=STALL, seeds=cd.SEARCH_SEEDS,
           workers=WORKERS, output_folder=None):
    """
    Run the GA for one case and GA seed and write ``ga_seed_<N>.csv`` to the output folder. The parameters
    after the GA seed are there for short test runs. The study uses their default values.

    Parameters:
        case (str): The case searched, a key of ``candidates.CASES``.
        ga_seed (int): The seed of the GA's own random numbers, which pick the starting candidates, the
            parents, the crossover points and the mutations.
        population (int): Candidates in each generation.
        generations (int): The most generations, counting the starting one.
        stall (int): Stop when the best candidate has not improved for this many generations.
        seeds (list): The search seeds.
        workers (int): Runs of the model at once.
        output_folder (str): Folder for the CSV file. None for the case's ``search`` folder.

    Returns:
        tuple: (the best candidate's 16 genes, its mean profit per day)
    """
    if output_folder is None:
        output_folder = os.path.join(cd.case_folder(case), "search")
    # The same starting candidates in every case, so that the cases differ only in the disruptions.
    rng = random.Random(f"genetic algorithm, starting candidates, seed {ga_seed}")
    starting_population = [cd.random_candidate(rng) for _ in range(population)]
    os.makedirs(output_folder, exist_ok=True)
    path = os.path.join(output_folder, f"ga_seed_{ga_seed}.csv")
    start = time.perf_counter()
    print(f"Case {case}, GA seed {ga_seed}: {population} candidates a generation, at most {generations} "
          f"generations, stop after {stall} without improvement; {len(seeds)} seeds each, {workers} workers")
    with open(path, "w", newline="") as file, Pool(processes=workers) as pool:
        scorer = cd.Scorer(pool, seeds, cd.CASES[case])
        writer = csv.writer(file)
        writer.writerow(["generation", "row"] + cd.candidate_columns(seeds))
        generation = 0
        not_valid = 0  # candidates that were not valid, over all generations
        best_so_far = None  # mean profit per day of the best candidate so far
        improved_in = 0  # the last generation in which the best candidate improved

        def fitness(ga, candidates, rows):
            """PyGAD's fitness function: the whole generation arrives in one call and runs as one batch."""
            return scorer.score(candidates, generation)

        def after_generation(ga):
            """
            Write the generation just scored, flush it to disk and print a line. Return "stop", which ends
            PyGAD's run, if the best candidate has not improved for ``stall`` generations.
            """
            nonlocal generation, not_valid, best_so_far, improved_in
            for row, genes in enumerate(ga.population):
                writer.writerow([generation, row] + scorer.describe(genes))
            not_valid += sum(not cd.is_valid(genes) for genes in ga.population)
            file.flush()
            os.fsync(file.fileno())
            best, best_per_day = scorer.best()
            if best_so_far is None or best_per_day > best_so_far:
                best_so_far, improved_in = best_per_day, generation
            print(f"  generation {generation}: best so far {best_per_day:.1f} rupees a day "
                  f"(since generation {improved_in}), {len(scorer.results)} candidates run, {not_valid} not valid")
            stalled = generation - improved_in >= stall
            generation += 1
            return "stop" if stalled else None

        ga = pygad.GA(num_generations=generations - 1,  # PyGAD does not count the starting generation
                      initial_population=starting_population,
                      gene_space=cd.GENE_RANGES,
                      gene_type=int,
                      num_parents_mating=min(PARENTS, population),
                      parent_selection_type="sss",  # steady-state selection: the highest scores are the parents
                      keep_elitism=KEEP_ELITISM,
                      crossover_type="single_point",
                      mutation_type=step_mutation,
                      fitness_func=fitness,
                      fitness_batch_size=population,  # a whole generation in one call
                      on_generation=after_generation,
                      random_seed=ga_seed)
        # PyGAD scores the starting generation without calling on_generation, so it is scored and written here.
        # run() then scores it again, which costs nothing, since every candidate in it has been run.
        fitness(ga, ga.population, None)
        after_generation(ga)
        ga.run()
    best, best_per_day = scorer.best()
    minutes = (time.perf_counter() - start) / 60
    reason = (f"no improvement for {stall} generations" if generation - 1 - improved_in >= stall
              else f"the limit of {generations} generations")
    print(f"Stopped after generation {generation - 1}: {reason}.")
    print(f"Done in {minutes:.1f} minutes. Best found: {best_per_day:.1f} rupees a day, found in generation "
          f"{improved_in}, {cd.settings_from_genes(best)}")
    print(f"{len(scorer.results)} candidates run ({len(scorer.results) * len(seeds)} runs), "
          f"{not_valid} not valid. Written to {path}")
    return list(best), best_per_day


def main():
    """
    Read the case and the GA seed from the command line and run the GA.

    Parameters:
        None

    Returns:
        None
    """
    parser = argparse.ArgumentParser(description="Search the (s, S) settings with a genetic algorithm.")
    parser.add_argument("--case", choices=list(cd.CASES), required=True,
                        help="none for no disruptions, or the mean days between disruptions of the bakery")
    parser.add_argument("--ga-seed", type=int, required=True, help="seed of the genetic algorithm, 1 to 5 in the study")
    arguments = parser.parse_args()
    run_ga(arguments.case, arguments.ga_seed)


if __name__ == "__main__":
    main()
