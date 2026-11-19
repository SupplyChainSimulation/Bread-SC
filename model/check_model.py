"""
Verification checks of the bread model in ``bread_model.py``.

Run it from the repository folder with ``python -m model.check_model``. It prints one line for each check and
ends with an exit code of 1 if any check fails. The checks are:

1. The same seed gives the same run.
2. Different settings run with the same seed face the same customers (common random numbers).
3. Units balance. At every site, the units that came in minus the units that went out equal the change in
   its inventory level. The raw materials the bakery received match the loaves it made. At every shop,
   the units delivered to customers plus the lost sales equal the units they ordered.
4. Profit parts add up: at every site, and for the whole network, where sales between sites cancel out.
5. No warning appears, in particular none about an order that can never be filled (a deadlock).
6. A run with no disruptions gives the same profit as before disruptions were added to the model.
7. With disruptions of the bakery, different settings run with the same seed face the same disruptions.
8. Each disruption lasts DISRUPTION_LENGTH days.
9. The bakery starts no production batch while it is disrupted, and the distributors' orders are blocked.

Checks 3 and 4 are made twice: with no disruptions, and with one disruption of the bakery per 50 days on
average, the most frequent case of the study.

The settings below are only for these checks. They are not a result of the study.

Functions:
    check: Records and prints the result of one check.
    trial_settings: Trial settings for the checks.
    check_same_seed: Check 1.
    check_same_customers: Check 2.
    check_units_balance: Check 3.
    check_profit_parts: Check 4.
    check_no_disruptions_unchanged: Check 6.
    check_same_disruptions: Check 7.
    check_disruption_length: Check 8.
    check_production_halted: Check 9.
    main: Runs every check and returns the exit code.
"""

import math
import sys
import warnings

import SupplyNetPy.Components as scm

from model import bread_model as bm

RESULTS = []  # (name, passed) for every check made

# Mean days between disruptions in the most frequent case of the study, so that a run has many of them.
CHECK_DAYS_BETWEEN = min(bm.DAYS_BETWEEN_DISRUPTIONS)

# Network profit of the trial settings, seed 1, with no disruptions, recorded with the model as it was before
# disruptions were added. A run with no disruptions must still give exactly this.
PROFIT_BEFORE_DISRUPTIONS = 106749.01826296141


def check(name, passed, detail=""):
    """
    Record and print the result of one check.

    Parameters:
        name (str): What was checked.
        passed (bool): Whether the check passed.
        detail (str): Numbers that show the result.

    Returns:
        None
    """
    RESULTS.append((name, bool(passed)))
    print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def close(a, b):
    """
    Whether two money values are equal up to rounding error.

    Parameters:
        a (float): First value.
        b (float): Second value.

    Returns:
        bool: True if they differ by less than one millionth of their size (or of 1).
    """
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)


def trial_settings(scale=1.0):
    """
    Trial (s, S) settings for the checks, in days of each site's mean demand. ``scale`` makes a second,
    different setting from the same rule.

    Parameters:
        scale (float): Factor applied to every setting.

    Returns:
        dict: The (s, S) settings of each site, as ``build_network`` takes them.
    """
    shop_demand = {shop: bm.ORDERS_PER_DAY[shop] * (bm.ORDER_SIZE_MIN + bm.ORDER_SIZE_MAX) / 2
                   for shop in bm.SHOPS}  # mean loaves per day
    demand = dict(shop_demand)
    # A distributor's demand is that of the shops for which it is the first supplier.
    demand["distributor1"] = shop_demand["shop1"] + shop_demand["shop2"] + shop_demand["shop3"]
    demand["distributor2"] = shop_demand["shop4"] + shop_demand["shop5"]
    demand["bakery"] = sum(shop_demand.values())
    # (reorder point, order-up-to level) in days of demand
    days = {"bakery": (0.5, 2.0), "distributor1": (1.0, 2.0), "distributor2": (1.0, 2.0)}
    days.update({shop: (0.5, 1.5) for shop in bm.SHOPS})
    settings = {}
    for site_id, (low, high) in days.items():
        s = max(1, round(low * scale * demand[site_id]))
        S = max(s + 1, round(high * scale * demand[site_id]))
        settings[site_id] = {"s": s, "S": S}
    return settings


def check_same_seed():
    """
    Check 1: two runs with the same settings and seed give the same results.

    Parameters:
        None

    Returns:
        None
    """
    settings = trial_settings()
    first = bm.run_network(settings, seed=1)
    second = bm.run_network(settings, seed=1)
    keys = ["profit", "revenue", "total_cost", "inventory_waste", "demand_by_customers",
            "fulfillment_received_by_customers", "demand_by_site"]
    same = all(first[k] == second[k] for k in keys)
    same = same and all(first["nodes"][n].stats.profit == second["nodes"][n].stats.profit for n in bm.SITES)
    check(f"the same seed gives the same run", same,
          f"profit {first['profit']:.2f} and {second['profit']:.2f}")


def check_same_customers():
    """
    Check 2: two different settings with the same seed face the same customer orders at every shop.

    Parameters:
        None

    Returns:
        None
    """
    low = bm.run_network(trial_settings(scale=1.0), seed=2)
    high = bm.run_network(trial_settings(scale=1.5), seed=2)
    same = all(low["demands"][f"customers_{s}"].stats.demand_placed
               == high["demands"][f"customers_{s}"].stats.demand_placed for s in bm.SHOPS)
    different_runs = low["profit"] != high["profit"]
    check(f"different settings face the same customers", same and different_runs,
          f"customer orders {low['demand_by_customers']} and {high['demand_by_customers']}; "
          f"profit {low['profit']:.0f} and {high['profit']:.0f}")


def _units_sent(sc, site_id):
    """
    The units a site has sent to its buyers so far. A replenishment order is counted at the buyer when it
    arrives, so units in transit are not yet in any statistic of the supplier. Instead, every unit ordered
    over a link has left the supplier unless the order is still waiting there (a backorder).

    Parameters:
        sc (dict): The supply chain network after a run.
        site_id (str): The ID of the supplier.

    Returns:
        float: Units ordered over the site's buyer links, minus units still waiting at the site.
    """
    node = sc["nodes"][site_id]
    return sum(link.stats.demand_placed[1] - link.stats.backorder[1] for link in node.buyers)


def _case_name(days_between_disruptions):
    """
    The words added to a check's name to say which case it ran.

    Parameters:
        days_between_disruptions (float): Mean days between disruptions of the bakery, or None for none.

    Returns:
        str: For example " (one disruption per 50 days)", or "" with no disruptions.
    """
    if days_between_disruptions is None:
        return ""
    return f" (one disruption per {days_between_disruptions} days)"


def check_units_balance(days_between_disruptions=None):
    """
    Check 3: units balance in a run with no warm-up, so that every count starts at time 0.

    Parameters:
        days_between_disruptions (float): Mean days between disruptions of the bakery, or None for none.

    Returns:
        None
    """
    sc = bm.run_network(trial_settings(), seed=3, days_between_disruptions=days_between_disruptions, warm_up=0)
    case = _case_name(days_between_disruptions)

    for site_id, (_, node_type, _, initial_level, _) in bm.SITES.items():
        node = sc["nodes"][site_id]
        stats = node.stats
        if node_type == "manufacturer":
            came_in = stats.total_products_manufactured
        else:
            came_in = stats.fulfillment_received[1]
        if node_type == "retailer":
            went_out = sc["demands"][f"customers_{site_id}"].stats.fulfillment_received[1]
        else:
            went_out = _units_sent(sc, site_id)
        expected = initial_level + came_in - went_out - stats.inventory_waste
        check(f"units balance at {site_id}{case}", expected == node.inventory.level,
              f"{initial_level} + {came_in} in - {went_out} out - {stats.inventory_waste} expired = {expected}, "
              f"inventory level {node.inventory.level}")
        if node_type == "retailer":
            check(f"no units dropped at {site_id}{case}", stats.dropped_qty == 0, f"{stats.dropped_qty}")

    # Raw materials: the grams received and not used, per gram per loaf, give the loaves started. A
    # production batch uses its raw materials when it starts and adds its loaves when it ends, so a
    # production batch still under way at the end has been started but not counted as made.
    bakery = sc["nodes"]["bakery"]
    made = bakery.stats.total_products_manufactured
    started = {}
    for link in bakery.suppliers:
        raw_id = link.source.raw_material.ID
        used = link.stats.fulfillment_received[1] - bakery.raw_inventory_counts[raw_id]
        started[raw_id] = used / bm.RAW_MATERIALS[raw_id][2]
    loaves = set(started.values())
    in_production = loaves.pop() - made if len(loaves) == 1 else None
    if bakery.production_cycle:
        ok = in_production is not None and 0 < in_production <= bm.BATCH_SIZE
    else:
        ok = in_production == 0
    check(f"raw materials used match the loaves made{case}", ok,
          f"loaves started from each raw material {started}, made {made}, "
          f"production batch under way: {bakery.production_cycle}")

    for shop_id in bm.SHOPS:
        customers = sc["demands"][f"customers_{shop_id}"].stats
        lost = sc["nodes"][shop_id].stats.lost_sales[1]
        ordered = customers.demand_placed[1]
        delivered = customers.fulfillment_received[1]
        check(f"delivered plus lost sales equal units ordered at {shop_id}{case}",
              delivered + lost == ordered, f"{delivered} + {lost} = {ordered}")

    # The links of a site add up to the site.
    for site_id in bm.SITES:
        node = sc["nodes"][site_id]
        over_links = sum(link.stats.fulfillment_received[1] for link in node.suppliers)
        if site_id == "bakery":
            continue  # its links carry grams of three raw materials, checked above
        check(f"links add up to the units received at {site_id}{case}",
              over_links == node.stats.fulfillment_received[1],
              f"{over_links} and {node.stats.fulfillment_received[1]}")


def check_profit_parts(days_between_disruptions=None):
    """
    Check 4: profit parts add up, in a run with a warm-up, at every site and for the whole network.

    Parameters:
        days_between_disruptions (float): Mean days between disruptions of the bakery, or None for none.

    Returns:
        None
    """
    sc = bm.run_network(trial_settings(), seed=4, days_between_disruptions=days_between_disruptions)
    case = _case_name(days_between_disruptions)
    nodes = sc["nodes"]

    for site_id in bm.SITES:
        stats = nodes[site_id].stats
        parts = stats.inventory_carry_cost + stats.inventory_spend_cost + stats.transportation_cost
        if site_id == "bakery":
            parts += stats.total_manufacturing_cost
        revenue = stats.demand_fulfilled[1] * nodes[site_id].sell_price
        ok = (close(parts, stats.node_cost) and close(revenue, stats.revenue)
              and close(stats.profit, stats.revenue - stats.node_cost))
        check(f"profit parts add up at {site_id}{case}", ok,
              f"revenue {stats.revenue:.2f} - cost {stats.node_cost:.2f} = profit {stats.profit:.2f}")

    distributors = ["distributor1", "distributor2"]
    bakery_sales = nodes["bakery"].stats.revenue
    distributor_purchases = sum(nodes[d].stats.inventory_spend_cost for d in distributors)
    check(f"the bakery's sales equal the distributors' purchases{case}",
          close(bakery_sales, distributor_purchases), f"{bakery_sales:.2f} and {distributor_purchases:.2f}")
    distributor_sales = sum(nodes[d].stats.revenue for d in distributors)
    shop_purchases = sum(nodes[s].stats.inventory_spend_cost for s in bm.SHOPS)
    check(f"the distributors' sales equal the shops' purchases{case}",
          close(distributor_sales, shop_purchases), f"{distributor_sales:.2f} and {shop_purchases:.2f}")

    # So network profit is what customers paid, minus what leaves the network: raw materials, manufacturing,
    # holding and transportation costs.
    customer_revenue = sum(nodes[s].stats.revenue for s in bm.SHOPS)
    bakery = nodes["bakery"].stats
    costs = (bakery.inventory_spend_cost + bakery.total_manufacturing_cost
             + sum(nodes[n].stats.inventory_carry_cost + nodes[n].stats.transportation_cost for n in bm.SITES))
    check(f"network profit is customer revenue minus the costs that leave the network{case}",
          close(sc["profit"], customer_revenue - costs),
          f"{customer_revenue:.2f} - {costs:.2f} = {customer_revenue - costs:.2f}, profit {sc['profit']:.2f}")
    site_profits = sum(nodes[n].stats.profit for n in bm.SITES)
    check(f"network profit is the sum of the site profits{case}", close(sc["profit"], site_profits),
          f"{site_profits:.2f} and {sc['profit']:.2f}")


def check_no_disruptions_unchanged():
    """
    Check 6: with no disruptions, the trial settings on seed 1 give the network profit recorded before
    disruptions were added to the model, so adding them changed nothing in the runs without them.

    Parameters:
        None

    Returns:
        None
    """
    profit = bm.run_network(trial_settings(), seed=1)["profit"]
    check("a run with no disruptions is as before disruptions were added", profit == PROFIT_BEFORE_DISRUPTIONS,
          f"profit {profit!r}, recorded {PROFIT_BEFORE_DISRUPTIONS!r}")


def check_same_disruptions():
    """
    Check 7: two different settings with the same seed face the same disruptions of the bakery, at the same
    times, and the same customers.

    Parameters:
        None

    Returns:
        None
    """
    low = bm.run_network(trial_settings(scale=1.0), seed=2, days_between_disruptions=CHECK_DAYS_BETWEEN)
    high = bm.run_network(trial_settings(scale=1.5), seed=2, days_between_disruptions=CHECK_DAYS_BETWEEN)
    starts = low["nodes"]["bakery"].disruption_starts
    same = starts == high["nodes"]["bakery"].disruption_starts and len(starts) > 0
    same = same and all(low["demands"][f"customers_{s}"].stats.demand_placed
                        == high["demands"][f"customers_{s}"].stats.demand_placed for s in bm.SHOPS)
    detail = (f"{len(starts)} disruptions, the first at day {starts[0]:.2f}; "
              f"profit {low['profit']:.0f} and {high['profit']:.0f}") if starts else "no disruption"
    check(f"different settings face the same disruptions{_case_name(CHECK_DAYS_BETWEEN)}",
          same and low["profit"] != high["profit"], detail)


def check_disruption_length():
    """
    Check 8: every disruption lasts DISRUPTION_LENGTH days. The library's total disrupted time of the bakery
    must equal that length for every disruption, except one still under way at the end of the run, which
    counts up to the end. Run with no warm-up, so that the statistics cover every disruption.

    Parameters:
        None

    Returns:
        None
    """
    end = bm.RUN_LENGTH
    sc = bm.run_network(trial_settings(), seed=5, days_between_disruptions=CHECK_DAYS_BETWEEN, warm_up=0,
                        run_length=end)
    bakery = sc["nodes"]["bakery"]
    starts = bakery.disruption_starts
    expected = sum(min(bm.DISRUPTION_LENGTH, end - start) for start in starts)
    ok = (len(starts) > 0 and bakery.stats.disruptions == len(starts)
          and close(bakery.stats.disrupted_time, expected))
    check(f"each disruption lasts {bm.DISRUPTION_LENGTH} days{_case_name(CHECK_DAYS_BETWEEN)}", ok,
          f"{len(starts)} disruptions, the library counts {bakery.stats.disruptions}; "
          f"disrupted for {bakery.stats.disrupted_time:.4f} days, expected {expected:.4f}")


def check_production_halted():
    """
    Check 9: the bakery starts no production batch while it is disrupted, and starts at least one at the
    moment a disruption ends (a production batch that had to wait). The distributors' orders are blocked
    while the bakery is disrupted (the library records them as ``blocked``). The start time of every
    production batch is recorded by wrapping the bakery's production batch once more, for this check only.

    A production batch has to wait only if the bakery has raw materials for planned loaves when a disruption
    starts, or they arrive during it. With the trial settings that happens in about 1 disruption in 5, so
    the check uses seed 2, in which 2 production batches wait.

    Parameters:
        None

    Returns:
        None
    """
    sc = bm.build_network(trial_settings(), seed=2, days_between_disruptions=CHECK_DAYS_BETWEEN)
    bakery = sc["nodes"]["bakery"]
    batch_starts = []
    make_production_batch = bakery.manufacture_product  # the model's version, which waits out a disruption

    def manufacture_product():
        made = yield from make_production_batch()
        if made > 0:  # the production batch started MANUFACTURING_TIME ago
            batch_starts.append(bakery.env.now - bm.MANUFACTURING_TIME)
        return made

    bakery.manufacture_product = manufacture_product
    scm.simulate_sc_net(sc, sim_time=bm.WARM_UP + bm.RUN_LENGTH, logging=False)

    starts = bakery.disruption_starts
    ends = [d + bm.DISRUPTION_LENGTH for d in starts]
    waited = [t for t in batch_starts if any(close(t, end) for end in ends)]
    during = [t for t in batch_starts if t not in waited and any(d <= t < end for d, end in zip(starts, ends))]
    case = _case_name(CHECK_DAYS_BETWEEN)
    check(f"no production batch starts while the bakery is disrupted{case}",
          len(starts) > 0 and not during and len(waited) > 0,
          f"{len(starts)} disruptions, {len(batch_starts)} production batches, {len(during)} started during a "
          f"disruption, {len(waited)} started when one ended")
    blocked = sum(sc["nodes"][d].stats.blocked[0] for d in ["distributor1", "distributor2"])
    check(f"the distributors' orders are blocked while the bakery is disrupted{case}", blocked > 0,
          f"{blocked} replenishment orders blocked")


def main():
    """
    Run every check, and report any warning raised.

    Parameters:
        None

    Returns:
        int: 0 if every check passed, 1 otherwise.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        check_same_seed()
        check_same_customers()
        check_units_balance()
        check_profit_parts()
        check_no_disruptions_unchanged()
        check_same_disruptions()
        check_disruption_length()
        check_production_halted()
        check_units_balance(CHECK_DAYS_BETWEEN)
        check_profit_parts(CHECK_DAYS_BETWEEN)
    messages = sorted({str(w.message) for w in caught})
    check("no warning appeared, including none about an order that can never be filled",
          not messages, "; ".join(messages))
    failed = [name for name, passed in RESULTS if not passed]
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
