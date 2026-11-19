"""
What the two search methods share: the candidates, their bounds, the step that changes a candidate, and how a
candidate is scored.

A candidate is one set of 16 integers, the reorder point s and the order-up-to level S of each of the 8 sites
that hold bread. Each integer is called a gene. Its score is its mean network profit over the 10 search seeds. Every candidate is run on the
same seeds, so all candidates face the same customers (common random numbers). A candidate seen before reuses
its score, so it is run only once.

A candidate with s at or above S at some site is not valid, since an (s, S) policy needs s < S. It is not run,
and its score is ``PENALTY``, far below the profit of any valid candidate, so that the search moves away from it.

The study searches each of its cases on its own: no disruptions of the bakery, and one disruption per 200,
100 or 50 days on average (``CASES``). A candidate's score is its mean profit in the case being searched.

Used by ``optimization/run_ga.py`` (genetic algorithm), ``optimization/run_sa.py`` (simulated annealing) and
``optimization/final_check.py``.

Functions:
    case_folder: The results folder of one case.
    settings_from_genes: Turn 16 genes into the settings ``model/bread_model.py`` takes.
    is_valid: Whether a candidate has s < S at every site.
    random_candidate: Draw one valid starting candidate.
    step: Change one gene of a candidate by a small random step.
    evaluate_run: Run one candidate on one seed (the work done by each worker process).
    candidate_columns: The CSV columns that describe a scored candidate.

Classes:
    Scorer: Runs candidates on the search seeds and keeps their results.
"""

import os
import statistics

from model import bread_model as bm

SEARCH_SEEDS = list(range(1001, 1011))  # 10 seeds, and every candidate is run on all of them

# The cases of the study, by name: the mean days between disruptions of the bakery, or None for none.
CASES = {"none": None}
CASES.update({str(days): days for days in bm.DAYS_BETWEEN_DISRUPTIONS})  # "200", "100", "50"
RESULTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
PENALTY = -1e9  # rupees, the score of a candidate that is not valid, far below any profit the model can make

# Search bounds on the order-up-to level S of each site, in loaves. The reorder point s runs from 0 to the
# site's largest S minus 1. A shop's largest S is its capacity.
S_LOWEST = 10
S_HIGHEST = {"bakery": 600, "distributor1": 300, "distributor2": 300,
             "shop1": 150, "shop2": 150, "shop3": 150, "shop4": 150, "shop5": 150}
SITE_IDS = list(bm.SITES)  # the order of the sites in a candidate: bakery, distributors, shops

# Genes 2i and 2i + 1 are the s and S of site i.
GENE_RANGES = []
for _site_id in SITE_IDS:
    GENE_RANGES.append(range(0, S_HIGHEST[_site_id]))               # s
    GENE_RANGES.append(range(S_LOWEST, S_HIGHEST[_site_id] + 1))    # S
GENE_NAMES = [f"{name}_{site_id}" for site_id in SITE_IDS for name in ("s", "S")]

# The largest change one step makes to a gene: 10% of the gene's range, rounded. For example 15 loaves for a
# shop's s (range 0 to 149) and 59 for the bakery's S (range 10 to 600).
STEP_FRACTION = 0.10
LARGEST_STEP = [max(1, round(STEP_FRACTION * len(gene_range))) for gene_range in GENE_RANGES]


def case_folder(case):
    """
    The results folder of one case, with a ``search`` and a ``final_check`` folder inside it. The results
    of the first search, with no disruptions and a fixed 60 generations, stay in ``results/search`` and
    ``results/final_check``.

    Parameters:
        case (str): The name of the case, a key of ``CASES``.

    Returns:
        str: For example ``optimization/results/disruption_per_50_days``, or
            ``optimization/results/no_disruptions`` for the case with no disruptions.
    """
    days = CASES[case]
    name = "no_disruptions" if days is None else f"disruption_per_{days}_days"
    return os.path.join(RESULTS_FOLDER, name)


def settings_from_genes(genes):
    """
    Turn a candidate's 16 genes into the (s, S) settings that ``model/bread_model.py`` takes.

    Parameters:
        genes (sequence): The 16 integers of a candidate, s and S of each site in the order of ``SITE_IDS``.

    Returns:
        dict: For each site ID, ``{'s': ..., 'S': ...}``.
    """
    return {site_id: {"s": int(genes[2 * i]), "S": int(genes[2 * i + 1])} for i, site_id in enumerate(SITE_IDS)}


def is_valid(genes):
    """
    Whether a candidate has s < S at every site.

    Parameters:
        genes (sequence): The 16 genes of the candidate.

    Returns:
        bool: True if s < S at all 8 sites.
    """
    return all(genes[2 * i] < genes[2 * i + 1] for i in range(len(SITE_IDS)))


def random_candidate(rng):
    """
    Draw one starting candidate. At each site, S is drawn from its range, and then s from 0 to S - 1, so
    that every starting candidate is valid.

    Parameters:
        rng (random.Random): The random number generator of the search.

    Returns:
        list: The 16 genes of the candidate.
    """
    genes = []
    for site_id in SITE_IDS:
        S = rng.randint(S_LOWEST, S_HIGHEST[site_id])
        s = rng.randint(0, S - 1)
        genes += [s, S]
    return genes


def step(genes, rng):
    """
    Change one gene of a candidate, picked at random, by a random whole number between 1 and the gene's
    ``LARGEST_STEP``, up or down. A value past the end of the gene's range is set to that end. The result may
    not be valid (for example, s moved up past S). The caller scores it with ``PENALTY``.

    Parameters:
        genes (sequence): The 16 genes of the candidate.
        rng (random.Random): The random number generator of the search.

    Returns:
        list: The 16 genes of the changed candidate (a new list).
    """
    genes = [int(g) for g in genes]
    i = rng.randrange(len(genes))
    change = rng.randint(1, LARGEST_STEP[i]) * rng.choice([-1, 1])
    genes[i] = min(max(genes[i] + change, GENE_RANGES[i][0]), GENE_RANGES[i][-1])
    return genes


def evaluate_run(args):
    """
    Run the model once, with the warm-up and run length of ``model/bread_model.py``. This is the work given
    to each worker process.

    Parameters:
        args (tuple): (genes, seed, days_between_disruptions), the 16 genes of a candidate, the seed of the
            run, and the mean days between disruptions of the bakery (None for none).

    Returns:
        dict: The network profit, the customer fill rate of the network and the expired units over the
            measured period.
    """
    genes, seed, days_between_disruptions = args
    sc = bm.run_network(settings_from_genes(genes), seed, days_between_disruptions)
    ordered = sum(sc["demands"][f"customers_{shop}"].stats.demand_placed[1] for shop in bm.SHOPS)
    delivered = sum(sc["demands"][f"customers_{shop}"].stats.fulfillment_received[1] for shop in bm.SHOPS)
    return {"profit": sc["profit"], "fill_rate": delivered / ordered, "expired_units": sc["inventory_waste"]}


def candidate_columns(seeds):
    """
    The CSV columns that describe a scored candidate, in the order ``Scorer.describe`` gives them.

    Parameters:
        seeds (list): The search seeds.

    Returns:
        list: The column names.
    """
    return (GENE_NAMES + ["valid", "first_seen", "mean_profit", "mean_profit_per_day", "mean_fill_rate",
                          "mean_expired_units"] + [f"profit_seed_{seed}" for seed in seeds])


class Scorer:
    """
    Runs candidates on the search seeds and keeps their results, so that a candidate is run only once.

    Parameters:
        pool (multiprocessing.Pool): The worker processes that run the model.
        seeds (list): The search seeds.
        days_between_disruptions (float): Mean days between disruptions of the bakery, or None for none.

    Attributes:
        results (dict): For each valid candidate run so far (a tuple of 16 genes), when it was first seen
            (the generation or the step) and the results of its runs, one dict per seed.
    """

    def __init__(self, pool, seeds, days_between_disruptions=None):
        self.pool = pool
        self.seeds = seeds
        self.days_between_disruptions = days_between_disruptions
        self.results = {}

    def mean_profit(self, genes):
        """
        The mean network profit of a valid candidate already run.

        Parameters:
            genes (sequence): The 16 genes of the candidate.

        Returns:
            float: The mean network profit over the search seeds, in rupees over the measured period.
        """
        return statistics.mean(run["profit"] for run in self.results[tuple(int(g) for g in genes)]["runs"])

    def score(self, candidates, seen):
        """
        Score a list of candidates. The valid ones not run before are run on all search seeds as one batch,
        spread over the workers.

        Parameters:
            candidates (sequence): The candidates, each a sequence of 16 genes.
            seen (int): The generation or the step these candidates belong to, recorded for new candidates.

        Returns:
            list: The score of each candidate: its mean network profit, or ``PENALTY`` if it is not valid.
        """
        keys = [tuple(int(g) for g in genes) for genes in candidates]
        new = []
        for key in keys:
            if is_valid(key) and key not in self.results and key not in new:
                new.append(key)
        runs = [(key, seed, self.days_between_disruptions) for key in new for seed in self.seeds]
        # chunksize=1 hands out one run at a time, so every worker stays busy to the end.
        outcomes = self.pool.map(evaluate_run, runs, chunksize=1)
        for i, key in enumerate(new):
            self.results[key] = {"first_seen": seen,
                                 "runs": outcomes[i * len(self.seeds):(i + 1) * len(self.seeds)]}
        return [self.mean_profit(key) if is_valid(key) else PENALTY for key in keys]

    def describe(self, genes):
        """
        The CSV values of a scored candidate, in the order of ``candidate_columns``. A candidate that is not
        valid was not run, so its results are left empty.

        Parameters:
            genes (sequence): The 16 genes of the candidate.

        Returns:
            list: The values.
        """
        key = tuple(int(g) for g in genes)
        if not is_valid(key):
            return list(key) + [False] + [""] * (5 + len(self.seeds))
        runs = self.results[key]["runs"]
        mean_profit = self.mean_profit(key)
        return (list(key) + [True, self.results[key]["first_seen"], mean_profit, mean_profit / bm.RUN_LENGTH,
                             statistics.mean(run["fill_rate"] for run in runs),
                             statistics.mean(run["expired_units"] for run in runs)]
                + [run["profit"] for run in runs])

    def best(self):
        """
        The valid candidate with the highest mean network profit so far.

        Returns:
            tuple: (its 16 genes, its mean network profit per day)
        """
        best = max(self.results, key=self.mean_profit)
        return best, self.mean_profit(best) / bm.RUN_LENGTH
