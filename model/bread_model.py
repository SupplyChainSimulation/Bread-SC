"""
The bread supply chain model of this study, built with SupplyNetPy 0.5.1.

The network has 3 raw-material suppliers (a flour mill, a sugar factory and a yeast factory), one bakery,
2 distributors and 5 shops, joined by 12 links. Each shop has its own customer demand. Bread is perishable.
The model is a new case study inspired by the bread example that comes with SupplyNetPy
(``examples/py/hybrid_big_sc.py``). Its parameter values are illustrative: they were chosen for this study,
not measured at a real bakery.

All parameter values are in the block below. Each comment gives the unit and the source of the value:
"example" means it is taken from the SupplyNetPy bread example, and "study" means it was set for this study.

Units used throughout:
    time: 1 time unit = 1 day
    bread: loaves (one unit of the product is one 400 g loaf)
    raw materials: grams (whole grams, so that the bakery's count of loaves it can make is exact)
    money: rupees

A tier is a level of the network whose sites hold bread, here the bakery, the distributors or the shops. The 8 sites that
hold bread are the bakery, the 2 distributors and the 5 shops. Each of them uses an (s, S) replenishment
policy (``SSReplenishment``), with its own settings.

Customer demand is stochastic. Lead times are fixed.

The bakery can be disrupted, for example by an equipment fault or a strike. A disruption lasts 2 days and
starts at random times. While it lasts, the bakery takes no replenishment orders from the distributors and
starts no production batch. A production batch already under way finishes. No units are destroyed. The study
runs the model with no disruptions and with one disruption per 200, 100 or 50 days on average.

Functions:
    build_network: Builds a fresh supply chain network for one run, from the settings and a seed.
    run_network: Builds the network, runs the warm-up, resets the statistics and runs the measured period.
    customer_fill_rate: The share of the units its customers ordered that one shop delivered.
"""

import random

import SupplyNetPy.Components as scm

# =====================================================================================================
# Parameter values
# =====================================================================================================

# ---- Raw materials --------------------------------------------------------------------------------
# The raw-material suppliers are infinite suppliers: they never run out. Network profit leaves infinite
# suppliers out, so what the bakery pays for raw materials is a real cost to the network.
RAW_MATERIALS = {
    # ID: (name, price in rupees per gram, grams per loaf)
    "flour": ("Flour", 0.040, 250),  # 40 rupees per kg (study)
    "sugar": ("Sugar", 0.045, 10),   # 45 rupees per kg (study)
    "yeast": ("Yeast", 0.40, 4),     # 400 rupees per kg (study)
}
# An infinite supplier does not mine, so these three values have no effect. The library requires them to
# be positive, so the example's values are kept: grams per round of mining, days per round, rupees per gram.
MINING = {
    "flour": (50, 1, 10),  # example
    "sugar": (30, 1, 8),   # example
    "yeast": (20, 1, 3),   # example
}

# ---- Bakery and the bread -------------------------------------------------------------------------
MANUFACTURING_COST = 10    # rupees per loaf for labour, energy and packaging (example)
MANUFACTURING_TIME = 1     # days per production batch (example)
BATCH_SIZE = 300           # loaves, the most made in one production batch (example)
SHELF_LIFE = 5             # days, counted from the manufacturing date, the same at all 8 sites (example)

# ---- Sell prices, in rupees per loaf ----------------------------------------------------------------
# Every buyer's buy price equals its supplier's sell price, so sales between sites cancel out of network
# profit. Every site sells at a markup over its buy price. A shop has a single buy price, and Shops 2 and 4
# buy from both distributors, so the two distributors must sell at the same price.
BAKERY_SELL_PRICE = 28       # study
DISTRIBUTOR_SELL_PRICE = 32  # study
SHOP_SELL_PRICE = 40         # example

# ---- Sites that hold bread ----------------------------------------------------------------------------
# ID: (name, node type, capacity in loaves, initial inventory level in loaves,
#      holding cost in rupees per loaf per day)
# Capacities: the bakery and the distributors have no capacity limit (study). With a finite capacity at a
# supplier, a buyer could place an order larger than the supplier can ever hold, and that order would never
# be filled. The shops keep a finite capacity, which must be at least the largest order-up-to level searched.
# Initial inventory levels are about 2 days of each site's demand (study). The warm-up removes their effect.
SITES = {
    "bakery":       ("Bakery",        "manufacturer", float("inf"), 125, 0.2),  # study
    "distributor1": ("Distributor 1", "distributor",  float("inf"), 70,  0.3),  # study
    "distributor2": ("Distributor 2", "distributor",  float("inf"), 55,  0.3),  # study
    "shop1":        ("Shop 1",        "retailer",     150,          30,  0.5),  # study
    "shop2":        ("Shop 2",        "retailer",     150,          15,  0.5),  # study
    "shop3":        ("Shop 3",        "retailer",     150,          25,  0.5),  # study
    "shop4":        ("Shop 4",        "retailer",     150,          20,  0.5),  # study
    "shop5":        ("Shop 5",        "retailer",     150,          35,  0.5),  # study
}
SHOPS = ["shop1", "shop2", "shop3", "shop4", "shop5"]

# Shops 2 and 4 have two suppliers. Each asks the supplier whose link was created first and turns to the
# other only when the first has too few units for the whole order (SelectAvailable, in dynamic mode, so the
# choice is made again for every replenishment order). The order of LINKS below therefore matters: l7 comes
# before l12, and l9 before l11.
SHOPS_WITH_TWO_SUPPLIERS = ["shop2", "shop4"]

# ---- Links ----------------------------------------------------------------------------------------
# ID: (source, sink, cost in rupees per replenishment order, lead time in days)
# The cost is paid by the buyer for every order. Costs are the example's costs times 10 (study). Lead times
# are fixed (study). They are the example's mean lead times (example), except l4: 1.1 days instead of 1.0
# (study), so that a delivery to Distributor 1 never arrives at the same moment as a production batch ends (a
# production batch takes 1 day). The longest lead time, 1.2 days on l5, stays well below the shelf life.
LINKS = {
    "l1":  ("flour_mill",    "bakery",       50, 0.3),
    "l2":  ("sugar_factory", "bakery",       60, 0.3),
    "l3":  ("yeast_factory", "bakery",       50, 0.3),
    "l4":  ("bakery",        "distributor1", 60, 1.1),
    "l5":  ("bakery",        "distributor2", 70, 1.2),
    "l6":  ("distributor1",  "shop1",        40, 0.4),
    "l7":  ("distributor1",  "shop2",        40, 0.5),
    "l8":  ("distributor1",  "shop3",        40, 0.6),
    "l9":  ("distributor2",  "shop4",        50, 0.5),
    "l10": ("distributor2",  "shop5",        50, 0.5),
    "l11": ("distributor1",  "shop4",        80, 0.5),
    "l12": ("distributor2",  "shop2",        60, 0.8),
}

# ---- Customer demand ----------------------------------------------------------------------------------
# Customer orders arrive at each shop one at a time, with exponential times between them (a Poisson
# process). Each order is for 1 to 4 loaves, each equally likely (example), a mean of 2.5 loaves.
# Mean demand per day: 15, 7.5, 12.5, 10 and 17.5 loaves, 62.5 in all, the example's total.
ORDERS_PER_DAY = {"shop1": 6, "shop2": 3, "shop3": 5, "shop4": 4, "shop5": 7}  # study
ORDER_SIZE_MIN = 1  # loaves (example)
ORDER_SIZE_MAX = 4  # loaves (example)
# A customer who finds too few loaves takes the loaves that are there and leaves. The rest are lost sales
# (study). Customers do not wait for loaves that are not there.
CONSUME_AVAILABLE = True

# ---- Disruptions of the bakery ------------------------------------------------------------------------
# A disruption of the bakery lasts DISRUPTION_LENGTH days. The time from the end of one disruption to the
# start of the next is exponential (disruptions arrive at random, independently of each other), with a mean
# of the case's mean days between disruptions minus DISRUPTION_LENGTH. So the mean time from the start of
# one disruption to the start of the next is the case's value.
DISRUPTION_LENGTH = 2                      # days (study)
DAYS_BETWEEN_DISRUPTIONS = [200, 100, 50]  # days, mean, one value for each case with disruptions (study)

# ---- Run length ---------------------------------------------------------------------------------------
# Set from the pilot runs (pilot/run_pilot.py).
WARM_UP = 30        # days
RUN_LENGTH = 365    # days, measured after the warm-up

# =====================================================================================================
# The model
# =====================================================================================================


def _check_settings(settings):
    """
    Check that the (s, S) settings cover the 8 sites that hold bread and fit the shops' capacities.
    The library cuts an order that would take a site past its capacity down to what fits, so an
    order-up-to level S above a shop's capacity would quietly act as the capacity. Such a setting is
    rejected here instead.

    Parameters:
        settings (dict): For each site ID, the reorder point and the order-up-to level,
            ``{'s': ..., 'S': ...}``.

    Returns:
        None. Raises ValueError if a setting is missing or does not fit.
    """
    if set(settings) != set(SITES):
        raise ValueError(f"Settings are needed for exactly these sites: {sorted(SITES)}")
    for site_id, param in settings.items():
        capacity = SITES[site_id][2]
        if not 0 <= param["s"] < param["S"]:
            raise ValueError(f"{site_id}: s must be at least 0 and S larger than s, got {param}")
        if param["S"] > capacity:
            raise ValueError(f"{site_id}: S = {param['S']} is above the capacity {capacity}")


def _make_product():
    """
    Create the raw materials and the bread. They are created afresh for every network, because the library
    stores values on these objects during a run.

    Parameters:
        None

    Returns:
        tuple: (dict of ``RawMaterial`` objects by raw material ID, the ``Product`` for the bread)
    """
    raw_materials = {}
    for raw_id, (name, price, _) in RAW_MATERIALS.items():
        quantity, time, mining_cost = MINING[raw_id]
        raw_materials[raw_id] = scm.RawMaterial(ID=raw_id, name=name, extraction_quantity=quantity,
                                                extraction_time=time, mining_cost=mining_cost, cost=price)
    bread = scm.Product(ID="bread", name="Bread", manufacturing_cost=MANUFACTURING_COST,
                        manufacturing_time=MANUFACTURING_TIME, sell_price=BAKERY_SELL_PRICE,
                        raw_materials=[(raw_materials[raw_id], RAW_MATERIALS[raw_id][2])
                                       for raw_id in RAW_MATERIALS],
                        batch_size=BATCH_SIZE)
    return raw_materials, bread


def _disruption_starts(bakery):
    """
    The bakery's disruption impact: the library calls it once, when a disruption of the bakery starts. It
    destroys nothing. It notes the time, and until when the bakery may start no production batch.

    Parameters:
        bakery (Manufacturer): The bakery.

    Returns:
        None
    """
    bakery.disruption_starts.append(bakery.env.now)
    bakery.production_halted_until = bakery.env.now + DISRUPTION_LENGTH


def _disruption_settings(seed, days_between_disruptions):
    """
    The settings that let the bakery be disrupted, added to its node in ``build_network``.

    The times between disruptions draw from their own random number generator, started from the seed. They
    use no other random numbers and nothing in them depends on the (s, S) settings, so every setting run with
    the same seed faces the same disruptions (common random numbers).

    Parameters:
        seed (int): The seed of this run.
        days_between_disruptions (float): Mean days from the start of one disruption to the start of the next.

    Returns:
        dict: Node settings for ``scm.create_sc_net``.
    """
    if days_between_disruptions <= DISRUPTION_LENGTH:
        raise ValueError(f"days_between_disruptions must be above {DISRUPTION_LENGTH}, "
                         f"got {days_between_disruptions}")
    rng = random.Random(f"bakery disruptions seed {seed}")
    mean_days_working = days_between_disruptions - DISRUPTION_LENGTH
    return {"node_disrupt_time": lambda: rng.expovariate(1 / mean_days_working),  # days until the next one
            "node_recovery_time": DISRUPTION_LENGTH,
            "disruption_impact": _disruption_starts}


def _halt_production_while_disrupted(bakery):
    """
    Make the bakery start no production batch while it is disrupted. The library lets a disrupted
    manufacturer go on making its product: a disruption only stops it from taking orders. In this model
    production stops too. A production batch already under way when a disruption starts finishes.

    The library's production loop calls ``bakery.manufacture_product()`` for each production batch. Here the
    bakery gets its own version of that method, which first waits until any disruption is over and then
    makes the production batch as the library does.

    Parameters:
        bakery (Manufacturer): The bakery, after ``scm.create_sc_net`` and before the run.

    Returns:
        None
    """
    make_production_batch = bakery.manufacture_product  # the library's method

    def manufacture_product():
        """One production batch, started only once the bakery is not disrupted (see above)."""
        if bakery.env.now < bakery.production_halted_until:
            # At the end of the disruption, the distributors whose orders were blocked order again, at the
            # same moment. Whether that happens just before or just after this production batch starts does
            # not change the batch: the raw materials for their loaves arrive 0.3 days later, and the batch
            # can only use raw materials already at the bakery.
            yield bakery.env.timeout(bakery.production_halted_until - bakery.env.now)
        made = yield from make_production_batch()
        return made

    bakery.manufacture_product = manufacture_product


def build_network(settings, seed, days_between_disruptions=None):
    """
    Build a fresh supply chain network for one run. A network can be run only once, so call this for every
    run.

    Each customer demand draws from its own random number generator, started from the seed. The same seed
    then gives the same customers, whatever the settings, so settings run with the same seeds can be
    compared fairly (common random numbers). Lead times are fixed, so they draw no random numbers. The
    disruptions of the bakery, if any, have their own generator too (see ``_disruption_settings``).

    Parameters:
        settings (dict): For each site ID in ``SITES``, the reorder point s and the order-up-to level S of
            its (s, S) policy, for example ``{'s': 20, 'S': 60}``.
        seed (int): The seed of this run.
        days_between_disruptions (float): Mean days from the start of one disruption of the bakery to the
            start of the next, or None for no disruptions.

    Returns:
        dict: The supply chain network, as returned by ``scm.create_sc_net``. With disruptions, the bakery
            (``sc["nodes"]["bakery"]``) also has ``disruption_starts``, the start times of its disruptions,
            warm-up included.
    """
    _check_settings(settings)
    raw_materials, bread = _make_product()

    nodes = []
    suppliers = {"flour": ("flour_mill", "Flour Mill"), "sugar": ("sugar_factory", "Sugar Factory"),
                 "yeast": ("yeast_factory", "Yeast Factory")}
    for raw_id, (supplier_id, name) in suppliers.items():
        nodes.append({"ID": supplier_id, "name": name, "node_type": "infinite_supplier",
                      "raw_material": raw_materials[raw_id], "logging": False})

    for site_id, (name, node_type, capacity, initial_level, holding_cost) in SITES.items():
        node = {"ID": site_id, "name": name, "node_type": node_type, "capacity": capacity,
                "initial_level": initial_level, "inventory_holding_cost": holding_cost,
                "replenishment_policy": scm.SSReplenishment, "policy_param": dict(settings[site_id]),
                "product": bread, "inventory_type": "perishable", "shelf_life": SHELF_LIFE,
                "logging": False}
        if node_type == "manufacturer":
            node["product_sell_price"] = BAKERY_SELL_PRICE
            if days_between_disruptions is not None:
                node.update(_disruption_settings(seed, days_between_disruptions))
        elif node_type == "distributor":
            node["product_buy_price"] = BAKERY_SELL_PRICE
            node["product_sell_price"] = DISTRIBUTOR_SELL_PRICE
        else:
            node["product_buy_price"] = DISTRIBUTOR_SELL_PRICE
            node["product_sell_price"] = SHOP_SELL_PRICE
            if site_id in SHOPS_WITH_TWO_SUPPLIERS:
                node["supplier_selection_policy"] = scm.SelectAvailable
                node["supplier_selection_mode"] = "dynamic"
        nodes.append(node)

    links = [{"ID": link_id, "source": source, "sink": sink, "cost": cost, "lead_time": lead_time}
             for link_id, (source, sink, cost, lead_time) in LINKS.items()]

    demands = []
    for shop_id in SHOPS:
        rng = random.Random(f"customers {shop_id} seed {seed}")
        rate = ORDERS_PER_DAY[shop_id]
        demands.append({"ID": f"customers_{shop_id}", "name": f"Customers of {SITES[shop_id][0]}",
                        "demand_node": shop_id,
                        # Default arguments fix this shop's own values inside the lambdas.
                        "order_arrival_model": lambda rng=rng, rate=rate: rng.expovariate(rate),
                        "order_quantity_model": lambda rng=rng: rng.randint(ORDER_SIZE_MIN, ORDER_SIZE_MAX),
                        "consume_available": CONSUME_AVAILABLE, "logging": False})

    sc = scm.create_sc_net(nodes=nodes, links=links, demands=demands)
    if days_between_disruptions is not None:
        bakery = sc["nodes"]["bakery"]
        bakery.disruption_starts = []
        bakery.production_halted_until = 0
        _halt_production_while_disrupted(bakery)
    return sc


def run_network(settings, seed, days_between_disruptions=None, warm_up=WARM_UP, run_length=RUN_LENGTH):
    """
    Build the network, run the warm-up, reset the statistics, and run the measured period. Initial inventory
    is free, so without a warm-up a setting that starts with many loaves would look better than it is.
    Disruptions happen in the warm-up too.

    Parameters:
        settings (dict): The (s, S) settings of each site (see ``build_network``).
        seed (int): The seed of this run.
        days_between_disruptions (float): Mean days between disruptions of the bakery, or None for none
            (see ``build_network``).
        warm_up (float): Days run before the statistics are reset. 0 for no warm-up.
        run_length (float): Days measured after the warm-up.

    Returns:
        dict: The supply chain network after the run, with the results of the measured period
            (for example ``sc["profit"]``).
    """
    sc = build_network(settings, seed, days_between_disruptions)
    if warm_up > 0:
        scm.simulate_sc_net(sc, sim_time=warm_up, logging=False)
        scm.reset_stats(sc)
    # sim_time is the time the run stops at, counted from 0, not the length of this part of the run.
    scm.simulate_sc_net(sc, sim_time=warm_up + run_length, logging=False)
    return sc


def customer_fill_rate(sc, shop_id):
    """
    The share of the units its customers ordered that a shop delivered, in the measured period.

    Parameters:
        sc (dict): The supply chain network after a run.
        shop_id (str): The ID of the shop, for example ``"shop1"``.

    Returns:
        float: Units delivered to the customers divided by units they ordered (None if they ordered none).
    """
    stats = sc["demands"][f"customers_{shop_id}"].stats
    ordered = stats.demand_placed[1]
    return stats.fulfillment_received[1] / ordered if ordered else None
