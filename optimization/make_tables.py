"""
Tables of the results of the search of the 4 cases: the best found settings of each case, and the cross-case check.

The cases are no disruptions of the bakery, and one disruption per 200, 100 or 50 days on average. Both tables are
made from files written earlier, with no new runs of the model:

- **Best found settings**, one column for each case and one row for each site: the settings (s / S, in loaves) of
  the GA seed with the highest mean profit in the case's final check, followed by rows for that mean profit on the
  new seeds 2001 to 2100 with its 95% confidence interval, the customer fill rate and the expired units a year. The
  CSV file has one row for each case instead. Read from each case's
  ``final_check/final_check_summary.csv``. The profit is the one on the new seeds, not the one on the search
  seeds, which is biased upward because the settings were picked on those seeds.
- **Cross-case check**, one row for each case the settings are run in and one column for each case the settings
  were found for. On the diagonal, the mean profit a day of the case's own settings. Elsewhere, the paired
  difference from the own settings, with 95% confidence intervals. Read from
  ``cross_case/cross_case_summary.csv``.

Run it from the repository folder, after the final checks and the cross-case check:

    python -m optimization.make_tables

It writes ``optimization/results/best_found_settings.csv``, and both tables in Markdown to
``optimization/results/tables.md``, ready to copy into ``optimization/README.md``.

Functions:
    best_found_rows: One row for each case, from the final checks.
    settings_table: The best found settings table in Markdown.
    cross_case_table: The cross-case table in Markdown.
    main: Write the CSV file and the tables.
"""

import csv
import os

from model import bread_model as bm
from optimization import candidates as cd

CASE_NAMES = {"none": "No disruptions", "200": "One per 200 days", "100": "One per 100 days",
              "50": "One per 50 days"}
SITE_NAMES = {"bakery": "Bakery", "distributor1": "Distributor 1", "distributor2": "Distributor 2",
              **{shop: f"Shop {i}" for i, shop in enumerate(bm.SHOPS, start=1)}}


def read_csv(path):
    """
    Read a CSV file.

    Parameters:
        path (str): Path of the file.

    Returns:
        list: One dict for each row.
    """
    with open(path, newline="") as file:
        return list(csv.DictReader(file))


def best_found_rows():
    """
    The best found settings of each case and their results on the new seeds, from the final checks.

    Parameters:
        None

    Returns:
        list: One dict for each case, in the order of ``candidates.CASES``, with the case, the GA seed, s and S of
            each site, the mean profit a day on seeds 2001 to 2100 and its 95% half-width, the customer fill rate
            and the expired units a year.
    """
    rows = []
    for case in cd.CASES:
        summary = read_csv(os.path.join(cd.case_folder(case), "final_check", "final_check_summary.csv"))
        leader = summary[0]["leader_ga_seed"]
        row = next(r for r in summary if r["ga_seed"] == leader)
        rows.append({"case": case, "ga_seed": int(leader),
                     **{name: int(row[name]) for name in cd.GENE_NAMES},
                     "mean_profit_per_day": float(row["check_mean_profit_per_day"]),
                     "half_width": float(row["check_half_width"]),
                     "mean_fill_rate": float(row["mean_fill_rate"]),
                     "mean_expired_units": float(row["mean_expired_units"])})
    return rows


def settings_table(rows):
    """
    The best found settings table in Markdown.

    Parameters:
        rows (list): As returned by ``best_found_rows``.

    Returns:
        str: The table, one column for each case and one row for each site (s / S), followed by rows for the mean
            profit a day on the new seeds, the customer fill rate and the expired units a year.
    """
    header = ["Site"] + [f"{CASE_NAMES[row['case']]} (GA seed {row['ga_seed']})" for row in rows]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for site, name in SITE_NAMES.items():
        lines.append("| " + " | ".join([name] + [f"{row['s_' + site]} / {row['S_' + site]}" for row in rows]) + " |")
    results = [("Mean profit a day, seeds 2001 to 2100",
                lambda r: f"{r['mean_profit_per_day']:.1f} ± {r['half_width']:.1f}"),
               ("Customer fill rate", lambda r: f"{r['mean_fill_rate']:.3f}"),
               ("Expired units a year", lambda r: f"{r['mean_expired_units']:,.0f}")]
    for name, cell in results:
        lines.append("| " + " | ".join([name] + [cell(row) for row in rows]) + " |")
    return "\n".join(lines)


def cross_case_table():
    """
    The cross-case table in Markdown: a row for each case the settings are run in, a column for each case the
    settings were found for.

    Parameters:
        None

    Returns:
        str: The table.
    """
    summary = {(r["evaluated_in_case"], r["settings_from_case"]): r
               for r in read_csv(os.path.join(cd.RESULTS_FOLDER, "cross_case", "cross_case_summary.csv"))}
    header = ["Run in case"] + [f"Values found for {CASE_NAMES[c].lower()}" for c in cd.CASES]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for run_in in cd.CASES:
        cells = [CASE_NAMES[run_in]]
        for found_for in cd.CASES:
            r = summary[(run_in, found_for)]
            if run_in == found_for:
                cells.append(f"**{float(r['mean_profit_per_day']):.1f} ± {float(r['half_width']):.1f}**")
            else:
                difference = f"{float(r['difference_from_own_per_day']):+.1f}".replace("-", "−")  # minus sign
                cells.append(f"{difference} ± {float(r['difference_half_width']):.1f}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    """
    Write ``optimization/results/best_found_settings.csv`` and both tables to ``optimization/results/tables.md``.

    Parameters:
        None

    Returns:
        None
    """
    rows = best_found_rows()
    path = os.path.join(cd.RESULTS_FOLDER, "best_found_settings.csv")
    with open(path, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("Wrote", path)
    path = os.path.join(cd.RESULTS_FOLDER, "tables.md")
    with open(path, "w", encoding="utf-8") as file:  # the tables hold ± and minus signs
        file.write("# Best values found\n\n" + settings_table(rows) + "\n\n# Cross-case check\n\n"
                   + cross_case_table() + "\n")
    print("Wrote", path)


if __name__ == "__main__":
    main()
