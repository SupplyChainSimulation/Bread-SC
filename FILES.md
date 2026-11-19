# Files in this repository

This page lists every file, what it is for, and for each Python script what it reads and writes. The README of each folder explains the method and the results. Run every script from the repository folder, as a module, so that Python finds the `model` folder.

| Folder | What it holds | Explained in |
|---|---|---|
| (top) | Summary of the study, license, Python packages, this overview | [README.md](README.md) |
| `model/` | The bread supply chain model and its verification checks | [model/README.md](model/README.md) |
| `pilot/` | Pilot runs that set the warm-up, the run length and the number of seeds, with their results | [pilot/README.md](pilot/README.md) |
| `optimization/` | The search, the final checks, the cross-case check and the baseline check, with their results, figures and tables | [optimization/README.md](optimization/README.md) |

Throughout, money is in rupees, and inventory levels and expired units are in loaves. A case is `none`, `200`, `100` or `50`, the mean days between disruptions of the bakery (`none` for no disruptions). Unless a file says otherwise, each run leaves out a 30-day warm-up and measures 365 days. An average inventory level is averaged over the 365 days, so that each level counts for as long as it lasted, and summed over the sites of the echelon, here the bakery, the 2 distributors or the 5 shops.

## Top folder

| File | Description |
|---|---|
| `README.md` | Summary of the study, the supply chain schematic, the main findings, and how to install and run |
| `FILES.md` | This overview |
| `LICENSE` | MIT license |
| `requirements.txt` | Exact versions of the Python packages used, including `supplynetpy==0.5.1` and `pygad==3.9.2` |
| `.gitignore` | Files Git leaves out |

## `model/`

| File | Description |
|---|---|
| `README.md` | The network with its diagram, the rules of the model, the parameter values and the verification |

### `bread_model.py`

The bread supply chain model, with 3 raw-material suppliers, the bakery, 2 distributors and 5 shops, joined by 12 links. The bakery can be disrupted. All parameter values sit in one block at the top of the file, each with its unit and source. It is a module, used by the other scripts, and is not run on its own.

| | |
|---|---|
| Reads | Nothing. The parameter values are in the file |
| Writes | Nothing |
| Gives | `build_network(settings, seed, days_between_disruptions=None)` returns a fresh network, not yet run, with no disruptions or with one disruption of the bakery per `days_between_disruptions` days on average. `run_network(settings, seed, days_between_disruptions=None)` returns the network after a 30-day warm-up and 365 measured days. `customer_fill_rate(sc, shop_id)` returns one shop's customer fill rate |

### `check_model.py`

The 84 verification checks of the model, listed in [model/README.md](model/README.md#verification).

| | |
|---|---|
| Run | `python -m model.check_model` (about 10 seconds) |
| Reads | `model/bread_model.py` |
| Writes | No files. Prints one line per check and the number passed. Exits with code 1 if any check fails |
| Gives | `trial_settings(scale)` returns the trial values of the checks, also used by the pilot and the baseline check |

## `pilot/`

| File | Description |
|---|---|
| `README.md` | What the pilot measures, its results, and the warm-up, run length and number of seeds it set |

### `run_pilot.py`

Pilot runs before the optimization. It times one run alone and several in parallel, records the first 120 days of each run for the warm-up, and finds the width of the confidence intervals with 10 and 30 seeds at run lengths of 182, 365 and 730 days. It uses the trial values at scales 0.5, 1.0, 1.1 and 2.0, and seeds 9001 to 9030, which no other script uses. The warm-up and the intervals are found for each of the 4 cases.

| | |
|---|---|
| Run | `python -m pilot.run_pilot` (one worker process per logical processor) |
| Reads | `model/bread_model.py`, and `trial_settings` from `model/check_model.py` |
| Writes | The three CSV files in `pilot/results/` below, and a printed summary |

### `plot_warm_up.py`

Draws the figure of the warm-up. For each case, it shows the mean over the 30 runs of a 7-day moving average of the daily network profit and of the inventory level of each echelon, with 95% confidence bands, for the trial values at scale 1.0. The profit axis is cut off at 700 a day, and the first days, which are higher because of the free initial inventory, are marked in the figure.

| | |
|---|---|
| Run | `python -m pilot.plot_warm_up` (about 10 seconds, on any computer, since it only reads a CSV file) |
| Reads | `pilot/results/warm_up.csv`, and `half_width` from `pilot/run_pilot.py` |
| Writes | `pilot/results/warm_up.png` |

### `results/`

`scale` is the factor on the trial values.

| File | One row per | Columns |
|---|---|---|
| `run_time.csv` | timing | `measure` (`alone`, or `parallel` for several runs at once), `case` (`none`, and `50` for one run alone), `scale`, `workers` (runs at once), `runs` (runs timed), `seconds_per_run` (wall-clock time divided by runs). Depends on the computer and its load |
| `warm_up.csv` | case, scale, seed and day, for the first 120 days, from time 0 with no warm-up | `case`, `scale`, `seed`, `day`, `profit` (network profit made that day), `expired_units` (that day), `inventory_level_bakery`, `inventory_level_distributors`, `inventory_level_shops` (at the end of the day, summed over the echelon's sites) |
| `replications.csv` | case, scale, seed and run length, after a 30-day warm-up | `case`, `scale`, `seed`, `run_length` (days measured), `profit` (network profit over the run length), `profit_per_year` (profit × 365 / run length), `fill_rate` (customer fill rate of the network), `expired_units` |
| `warm_up.png` | the figure drawn by `plot_warm_up.py` from `warm_up.csv` | one panel for each case, profit above and inventory level by echelon below |

## `optimization/`

| File | Description |
|---|---|
| `README.md` | The search problem, the genetic algorithm, the checks after the search, and all the results with their figures and tables |

We wrote two search methods, a genetic algorithm (GA) and simulated annealing (SA). Both search the same 16 integers, s and S of each of the 8 sites that hold bread, and score a candidate by its mean network profit over the search seeds 1001 to 1010. Running a seed again overwrites its file and gives the same results, whatever the number of worker processes. We use the GA, on GA seeds 1 to 5. We tested SA on SA seed 1 only, and it is not part of the results.

We ran two searches.

- **The first search** has no disruptions and a fixed 60 generations (3,000 candidates) in each GA seed. Its results are in `results/search/` and `results/final_check/`. We made it with the version of `run_ga.py` and `final_check.py` in commit b7bb0d7, which took `--ga-seed` only. We keep it for comparison.
- **The search of the 4 cases** searches each case on its own, and stops when the best candidate has not improved for 20 generations, or after 150 generations. The results of each case are in its own folder, `results/no_disruptions/`, `results/disruption_per_200_days/`, `results/disruption_per_100_days/` or `results/disruption_per_50_days/`. Each has a `search/` and a `final_check/` folder, laid out as `results/search/` and `results/final_check/` below.

### `candidates.py`

What the two methods share. It holds the cases and their results folders, the search bounds, a random valid starting candidate, the step that changes one gene by up to 10% of its range, the run of one candidate on one seed, and the scoring, which reuses earlier scores. A candidate with s at or above S at some site is not valid. It is not run and gets a score far below any profit. It is a module, used by the scripts below, and is not run on its own.

| | |
|---|---|
| Reads | `model/bread_model.py` |
| Writes | Nothing |

### `run_ga.py`

The GA, built on PyGAD. A generation has 50 candidates. Each generation keeps the best candidate and makes 49 children from the 25 best by single-point crossover, and each child then takes one step. The GA stops when the best candidate has not improved for 20 generations, or after 150 generations, counting the starting one.

| | |
|---|---|
| Run | `python -m optimization.run_ga --case C --ga-seed N`, for C = `none`, `200`, `100` or `50` and N = 1 to 5 (about 0.7 minutes a generation on 8 cores) |
| Reads | `model/bread_model.py`, `optimization/candidates.py` |
| Writes | `ga_seed_N.csv` in the case's `search/` folder (for example `optimization/results/disruption_per_50_days/search/`), laid out as in `results/search/` below, one generation at a time, and a line per generation on the screen |

### `run_sa.py`

SA. From a random valid starting candidate, each step takes one step from the current candidate. A better candidate is always accepted. A worse one is accepted with a probability that falls as the temperature falls, from 100 to 1 rupee a day over 3,000 steps. The result is the best candidate seen.

| | |
|---|---|
| Run | `python -m optimization.run_sa --sa-seed N`, for N = 1 to 5 (52 minutes for SA seed 1 on 10 worker processes) |
| Reads | `model/bread_model.py`, `optimization/candidates.py` |
| Writes | `optimization/results/search/sa_seed_N.csv` below, one step at a time, and a line every 100 steps on the screen |

### `results/search/`

Means are over the 10 search seeds. A candidate that is not valid has empty results.

Both files share these columns. `s_<site>` and `S_<site>` for each site, `valid` (`True` if s < S at every site), `first_seen` (the generation or step the candidate was first run in, and an earlier one than the row's means its score was reused), `mean_profit` (network profit over the 365 days), `mean_profit_per_day`, `mean_fill_rate` (customer fill rate of the network), `mean_expired_units`, `profit_seed_1001` to `profit_seed_1010` (network profit of each run).

| File | One row per | Columns before and after the shared ones |
|---|---|---|
| `ga_seed_N.csv` | candidate in each generation of GA seed N (50 × 60 rows in the first search, 50 × the generations run in the search of the 4 cases) | before, `generation` (0 for the starting candidates) and `row` (place in the generation, where row 0 from generation 1 on is the best candidate of the generation before) |
| `sa_seed_N.csv` | step of SA seed N (3,000 rows), describing the candidate tried at that step. Written by `run_sa.py`, but we do not keep it in the repository | before, `step` (0 for the starting candidate) and `temperature` (rupees a day). After, `accepted` (`True` if it became the current candidate), `current_profit_per_day` (of the current candidate after this step) and `best_profit_per_day` (of the best candidate so far) |

### `final_check.py`

The final check of one case. The best values found by GA seeds 1 to 5 are run on seeds 2001 to 2100, which the search never used, all on the same seeds and in the same case. For each set of values it reports (a) its mean profit on the search seeds, read from `ga_seed_N.csv`, (b) its mean profit on the new seeds with a 95% confidence interval, and (c) its paired difference in profit, seed by seed, from the set with the highest mean in (b), with a 95% confidence interval. It also reports the customer fill rate, the expired units and the average inventory level of each echelon.

| | |
|---|---|
| Run | `python -m optimization.final_check --case C`, after GA seeds 1 to 5 of case C (500 runs, about 2 minutes). `--ga-seeds` checks other GA seeds, for example `--ga-seeds 1 2` |
| Reads | `model/bread_model.py`, `optimization/candidates.py`, `ga_seed_N.csv` in the case's `search/` folder |
| Writes | `final_check_runs.csv` and `final_check_summary.csv` in the case's `final_check/` folder, laid out as in `results/final_check/` below, and a summary on the screen |

### `results/final_check/`

Expired units are over the 365 days.

| File | One row per | Columns |
|---|---|---|
| `final_check_runs.csv` | GA seed and check seed (5 × 100 rows) | `ga_seed` (whose best values found were run), `seed` (2001 to 2100), `profit` (network profit over the 365 days), `profit_per_day`, `fill_rate` (customer fill rate of the network), `expired_units`, `avg_inventory_level_bakery`, `avg_inventory_level_distributors`, `avg_inventory_level_shops` |
| `final_check_summary.csv` | GA seed (5 rows) | `ga_seed`, `s_<site>` and `S_<site>` for each site (its best values found), `search_mean_profit_per_day` (a), `check_mean_profit_per_day` (b), `check_half_width` (of the 95% confidence interval of (b)), `upward_bias_per_day` ((a) − (b)), `leader_ga_seed` (the GA seed with the highest mean in (b)), `difference_from_leader_per_day` (c), `difference_half_width` (of the 95% confidence interval of (c), 0 for the leader itself), `mean_fill_rate`, `mean_expired_units`, `mean_avg_inventory_level_bakery`, `mean_avg_inventory_level_distributors`, `mean_avg_inventory_level_shops` (means over the 100 check seeds) |

### `cross_case_check.py`

The cross-case check. The best values found for each case (those of the GA seed with the highest mean profit in the case's final check) are run in every case, on seeds 2001 to 2100. For each case it reports the mean profit of each set of values with a 95% confidence interval, and its paired difference, seed by seed, from the values found for that case. It also reports the customer fill rate, the expired units and the average inventory level of each echelon.

| | |
|---|---|
| Run | `python -m optimization.cross_case_check`, after `final_check.py` has been run for all 4 cases (1,600 runs, about 3 to 6 minutes) |
| Reads | `model/bread_model.py`, `optimization/candidates.py`, `optimization/final_check.py`, and `final_check_summary.csv` in each case's `final_check/` folder |
| Writes | `cross_case_runs.csv` and `cross_case_summary.csv` in `optimization/results/cross_case/`, laid out as below, and a summary on the screen |

### `results/cross_case/`

Expired units are over the 365 days.

| File | One row per | Columns |
|---|---|---|
| `cross_case_runs.csv` | set of values, case run in and check seed (4 × 4 × 100 rows) | `settings_from_case` (the case the values were found for), `evaluated_in_case`, `seed` (2001 to 2100), `profit`, `profit_per_day`, `fill_rate`, `expired_units`, `avg_inventory_level_bakery`, `avg_inventory_level_distributors`, `avg_inventory_level_shops` |
| `cross_case_summary.csv` | set of values and case run in (16 rows) | `evaluated_in_case`, `settings_from_case`, `settings_ga_seed` (the GA seed the values came from), `mean_profit_per_day`, `half_width` (of its 95% confidence interval), `difference_from_own_per_day` (from the values found for `evaluated_in_case`), `difference_half_width` (0 when the values are the case's own), `mean_fill_rate`, `mean_expired_units`, `mean_avg_inventory_level_bakery`, `mean_avg_inventory_level_distributors`, `mean_avg_inventory_level_shops` (means over the 100 check seeds) |

### `baseline_check.py`

The baseline check. It runs the trial values of `model/check_model.py` at scale 1.0, which no search found, in the 4 cases on the 10 search seeds (1001 to 1010). All cases use the same seeds, so a seed has the same customers in every case and the differences from the case with no disruptions are paired.

| | |
|---|---|
| Run | `python -m optimization.baseline_check` (40 runs, about 10 seconds on 8 cores) |
| Reads | `model/bread_model.py`, `model/check_model.py` (for the trial values), `optimization/candidates.py`, `optimization/final_check.py` |
| Writes | `baseline_runs.csv` and `baseline_summary.csv` in `optimization/results/baseline/`, laid out as below, and a summary on the screen |

### `results/baseline/`

| File | One row per | Columns |
|---|---|---|
| `baseline_runs.csv` | case and seed (4 × 10 rows) | `case`, `seed` (1001 to 1010), `profit`, `profit_per_day`, `fill_rate`, `expired_units` (over the 365 days), `avg_inventory_level_bakery`, `avg_inventory_level_distributors`, `avg_inventory_level_shops` |
| `baseline_summary.csv` | case (4 rows) | `case`, `mean_profit_per_day`, `profit_half_width` (of its 95% confidence interval), `difference_from_none_per_day` (paired by seed, from the case with no disruptions), `difference_half_width`, `mean_expired_units_per_day`, `expired_half_width`, `mean_fill_rate` |

### `plot_convergence.py`

Draws the convergence of the GA in the search of the 4 cases, with one panel for each case and one line for each GA seed. The x-axis is the number of runs of the model so far, which is the distinct valid candidates run so far times the 10 search seeds. A candidate seen before or not valid adds no runs. The y-axis is the best mean profit a day on the search seeds so far, with one point per generation. A filled dot marks a GA seed stopped by the stall rule, and an open dot one stopped at the cap of 150 generations. The y-axis starts at 300 a day, so the first generations, which lose money, are not shown.

| | |
|---|---|
| Run | `python -m optimization.plot_convergence`, after the searches of the 4 cases (a few seconds, on any computer) |
| Reads | `ga_seed_N.csv` in each case's `search/` folder, `optimization/candidates.py`, and `GENERATIONS` from `optimization/run_ga.py` |
| Writes | `optimization/results/convergence.png` |

### `plot_disruptions.py`

Draws two figures of how disruptions of the bakery change the results under the baseline values, the network profit a day and the expired units a day, against the disruption rate. The disruption rate is the number of disruptions of the bakery that start per day, 0, 1/200 = 0.005, 1/100 = 0.01 or 1/50 = 0.02. Each point is a mean over the 10 search seeds with its 95% confidence interval, and the 10 seeds are drawn as small dots. The points come from the runs of `baseline_check.py`, so no new runs are made.

| | |
|---|---|
| Run | `python -m optimization.plot_disruptions`, after `baseline_check.py` (a few seconds, on any computer) |
| Reads | `optimization/results/baseline/baseline_runs.csv`, `optimization/candidates.py`, and `half_width` from `optimization/baseline_check.py` |
| Writes | `optimization/results/disruption_profit.png` and `optimization/results/disruption_expired_units.png`, and the values drawn on the screen |

### `plot_pareto.py`

Draws the Pareto front of mean profit and mean customer fill rate in each case, the candidates that no other candidate of the case beats on both. Each case's candidates are the distinct valid candidates of its 5 GA seeds together, with their means on the search seeds. The y-axis starts at 200 a day, and the title counts the front points below it.

| | |
|---|---|
| Run | `python -m optimization.plot_pareto`, after the searches of the 4 cases (a few seconds, on any computer) |
| Reads | `ga_seed_N.csv` in each case's `search/` folder, `optimization/candidates.py` |
| Writes | `optimization/results/pareto.png` and `optimization/results/pareto_front.csv` |

### `make_tables.py`

Makes two tables from files written earlier, with no new runs. The first gives the best values found for each case, from the case's final check, with one column for each case and one row for each site, then rows for the mean profit a day on seeds 2001 to 2100, the customer fill rate and the expired units a year. The second is the cross-case check, with the mean profit of each case's own values on the diagonal and the paired differences elsewhere.

| | |
|---|---|
| Run | `python -m optimization.make_tables`, after the final checks and the cross-case check (a second, on any computer) |
| Reads | `final_check_summary.csv` in each case's `final_check/` folder, `optimization/results/cross_case/cross_case_summary.csv` |
| Writes | `optimization/results/best_found_settings.csv` and `optimization/results/tables.md` |

### Figures and tables in `results/`

| File | What it holds |
|---|---|
| `convergence.png` | The figure drawn by `plot_convergence.py` |
| `disruption_profit.png`, `disruption_expired_units.png` | The figures drawn by `plot_disruptions.py` (the baseline values in each case) |
| `pareto.png` | The figure drawn by `plot_pareto.py` |
| `pareto_front.csv` | One row per point on a front, with `case`, `s_<site>` and `S_<site>` for each site, `ga_seed` (the first GA seed that ran the candidate), `mean_profit_per_day`, `mean_fill_rate` and `mean_expired_units` (over the 365 days), all means over the 10 search seeds |
| `best_found_settings.csv` | One row per case, with `case`, `ga_seed` (the leader of the case's final check), `s_<site>` and `S_<site>` for each site, `mean_profit_per_day` (on seeds 2001 to 2100), `half_width` (of its 95% confidence interval), `mean_fill_rate` and `mean_expired_units` (a year) |
| `tables.md` | The table of the best values found and the cross-case table in Markdown, used in [optimization/README.md](optimization/README.md) |
| `network_schematic.png` | The schematic of the supply chain, with the sites by node type, each link with its lead time, and each shop's customers with the loaves they ask for in a day. Used in [README.md](README.md) and [model/README.md](model/README.md) |
| `network_diagrams.pdf` | The network with its parameter values, 5 pages. Page 1 is the schematic above. Pages 2 to 5 take one case each, no disruptions and one disruption per 200, 100 and 50 days. On them each site shows its best values of s and S found for that case (from `best_found_settings.csv`), its prices, holding cost and initial inventory level, and each link its lead time and cost. Each shop's customers show how often their orders arrive and how large they are, and in the cases with disruptions the bakery shows how long a disruption lasts and how often one starts. The subtitle of each page gives the case's mean profit a day on seeds 2001 to 2100 and its customer fill rate |
