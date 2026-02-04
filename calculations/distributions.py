import pandas as pd
import numpy as np

def calculate_waterfall_distribution(cash_available, lp_equity, gp_equity,
                                     pref_rate, gp_profit_share,
                                     lp_cumulative_deficit, gp_cumulative_deficit,
                                     include_catchup=False):
    """
    Calculate waterfall distribution for a given year

    Args:
        cash_available: Cash available for distribution this year
        lp_equity: LP's equity contribution
        gp_equity: GP's equity contribution
        pref_rate: Preferred return rate (%)
        gp_profit_share: GP's profit share after pref (%)
        lp_cumulative_deficit: LP's cumulative pref deficit from prior years
        gp_cumulative_deficit: GP's cumulative pref deficit from prior years
        include_catchup: Whether to include GP catch-up tier

    Returns:
        Dictionary with distribution details
    """

    total_equity = lp_equity + gp_equity
    lp_equity_pct = lp_equity / total_equity if total_equity > 0 else 0
    gp_equity_pct = gp_equity / total_equity if total_equity > 0 else 0

    # Calculate current year pref
    lp_pref_current = lp_equity * (pref_rate / 100)
    gp_pref_current = gp_equity * (pref_rate / 100)
    total_pref_current = lp_pref_current + gp_pref_current

    # Total pref owed (current + cumulative deficit)
    lp_total_pref_owed = lp_pref_current + lp_cumulative_deficit
    gp_total_pref_owed = gp_pref_current + gp_cumulative_deficit
    total_pref_owed = lp_total_pref_owed + gp_total_pref_owed

    # Initialize distribution amounts
    lp_pref_paid = 0
    gp_pref_paid = 0
    gp_catchup = 0
    lp_split = 0
    gp_split = 0

    remaining_cash = cash_available

    # Tier 1: Return OF capital (if needed, but typically not in cash flow distributions)
    # Skipping for now as we're focused on cash flow distributions

    # Tier 2: Preferred return (including catch-up of unpaid pref)
    if remaining_cash > 0 and total_pref_owed > 0:
        pref_payment = min(remaining_cash, total_pref_owed)

        # Split pref payment pro-rata between LP and GP based on amounts owed
        if total_pref_owed > 0:
            lp_pref_paid = pref_payment * (lp_total_pref_owed / total_pref_owed)
            gp_pref_paid = pref_payment * (gp_total_pref_owed / total_pref_owed)

        remaining_cash -= pref_payment

    # Update cumulative deficits
    new_lp_deficit = lp_total_pref_owed - lp_pref_paid
    new_gp_deficit = gp_total_pref_owed - gp_pref_paid

    # Tier 3: GP Catch-up (optional)
    if include_catchup and remaining_cash > 0:
        # GP catch-up brings GP to their profit share percentage of all profits distributed so far
        # Target: GP should have gp_profit_share% of (lp_pref_paid + gp_pref_paid + gp_catchup)
        # Solve: gp_catchup such that (gp_pref_paid + gp_catchup) = gp_profit_share% * (lp_pref_paid + gp_pref_paid + gp_catchup)

        total_distributed_before_catchup = lp_pref_paid + gp_pref_paid

        if gp_profit_share > 0:
            # gp_catchup = (gp_profit_share/100 * total_before) / (1 - gp_profit_share/100) - gp_pref_paid
            target_gp_catchup = (gp_profit_share / 100 * total_distributed_before_catchup) / (1 - gp_profit_share / 100)
            gp_catchup = min(remaining_cash, max(0, target_gp_catchup))
            remaining_cash -= gp_catchup

    # Tier 4: Remaining split according to profit share
    if remaining_cash > 0:
        lp_split = remaining_cash * ((100 - gp_profit_share) / 100)
        gp_split = remaining_cash * (gp_profit_share / 100)
        remaining_cash = 0

    # Total distributions
    lp_total = lp_pref_paid + lp_split
    gp_total = gp_pref_paid + gp_catchup + gp_split

    return {
        'cash_available': cash_available,

        # Tier 2: Pref
        'lp_pref_current': lp_pref_current,
        'gp_pref_current': gp_pref_current,
        'lp_pref_owed': lp_total_pref_owed,
        'gp_pref_owed': gp_total_pref_owed,
        'lp_pref_paid': lp_pref_paid,
        'gp_pref_paid': gp_pref_paid,

        # Tier 3: Catch-up
        'gp_catchup': gp_catchup,

        # Tier 4: Split
        'lp_split': lp_split,
        'gp_split': gp_split,

        # Totals
        'lp_total': lp_total,
        'gp_total': gp_total,
        'total_distributed': lp_total + gp_total,

        # Cumulative deficits for next year
        'new_lp_deficit': new_lp_deficit,
        'new_gp_deficit': new_gp_deficit
    }


def calculate_multi_year_waterfall(cf_df, lp_equity, gp_equity, pref_rate,
                                   gp_profit_share, include_catchup=False):
    """
    Calculate waterfall distributions for all years in cash flow projection

    Args:
        cf_df: DataFrame with cash flow projections (must have 'Year' and 'Cash Available' columns)
        lp_equity: LP's total equity contribution
        gp_equity: GP's total equity contribution
        pref_rate: Preferred return rate (%)
        gp_profit_share: GP's profit share after pref (%)
        include_catchup: Whether to include GP catch-up tier

    Returns:
        DataFrame with waterfall distributions by year
    """

    waterfall_data = []
    lp_cumulative_deficit = 0
    gp_cumulative_deficit = 0
    lp_cumulative_pref_paid = 0
    gp_cumulative_pref_paid = 0
    lp_cumulative_distributions = 0
    gp_cumulative_distributions = 0

    for _, row in cf_df.iterrows():
        year = row['Year']
        cash_available = row['Cash Available']

        dist = calculate_waterfall_distribution(
            cash_available, lp_equity, gp_equity,
            pref_rate, gp_profit_share,
            lp_cumulative_deficit, gp_cumulative_deficit,
            include_catchup
        )

        # Update cumulative tracking
        lp_cumulative_deficit = dist['new_lp_deficit']
        gp_cumulative_deficit = dist['new_gp_deficit']
        lp_cumulative_pref_paid += dist['lp_pref_paid']
        gp_cumulative_pref_paid += dist['gp_pref_paid']
        lp_cumulative_distributions += dist['lp_total']
        gp_cumulative_distributions += dist['gp_total']

        waterfall_data.append({
            'Year': year,
            'Cash Available': cash_available,

            # LP Distribution
            'LP Pref': dist['lp_pref_paid'],
            'LP Split': dist['lp_split'],
            'LP Total': dist['lp_total'],
            'LP Cumulative': lp_cumulative_distributions,

            # GP Distribution
            'GP Pref': dist['gp_pref_paid'],
            'GP Catch-up': dist['gp_catchup'],
            'GP Split': dist['gp_split'],
            'GP Total': dist['gp_total'],
            'GP Cumulative': gp_cumulative_distributions,

            # Deficits
            'LP Pref Deficit': lp_cumulative_deficit,
            'GP Pref Deficit': gp_cumulative_deficit
        })

    return pd.DataFrame(waterfall_data)
