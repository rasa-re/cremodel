import pandas as pd
import numpy as np

def calculate_noi_projection(year_1_noi, rent_growth_rate, years):
    """Calculate NOI for each year with compound rent growth - LEGACY FUNCTION"""
    noi_schedule = []
    for year in range(1, years + 1):
        noi = year_1_noi * ((1 + rent_growth_rate/100) ** (year - 1))
        noi_schedule.append({
            'Year': year,
            'NOI': noi
        })
    return pd.DataFrame(noi_schedule)

def calculate_lease_runway(years_elapsed, original_term, currently_in,
                          num_options_total, option_term_years):
    """Calculate lease runway scenarios"""

    # Determine current position
    if currently_in == "Original Term":
        current_term_remaining = original_term - years_elapsed
        options_used = 0
    else:
        # Extract option number (e.g., "1st Renewal Option" -> 1)
        if '1st' in currently_in:
            option_number = 1
        elif '2nd' in currently_in:
            option_number = 2
        elif '3rd' in currently_in:
            option_number = 3
        elif '4th' in currently_in:
            option_number = 4
        elif '5th' in currently_in:
            option_number = 5
        else:
            option_number = 1

        options_used = option_number

        # Calculate years into current option
        years_into_option = years_elapsed - original_term - ((option_number - 1) * option_term_years)
        current_term_remaining = option_term_years - years_into_option

    options_remaining = num_options_total - options_used

    return {
        'current_term_remaining': current_term_remaining,
        'options_used': options_used,
        'options_remaining': options_remaining,
        'max_total_runway': current_term_remaining + (options_remaining * option_term_years)
    }

def calculate_noi_projection_with_lease(base_rent, rent_structure_type, bump_frequency,
                                       bump_pct, annual_escalator, years,
                                       current_term_remaining, lease_runway, years_elapsed):
    """
    Calculate NOI based on actual lease terms and renewal options.
    base_rent: the rent the tenant is paying RIGHT NOW at acquisition (Year 1 = base_rent).
    years_elapsed: years since original lease commencement (used to align future bump dates).
    Bumps only apply when crossing a bump boundary beyond the current position.
    """
    noi_schedule = []

    # For fixed bumps: figure out how many bumps have already fired at acquisition
    # so we only apply incremental bumps going forward
    if rent_structure_type == "Fixed Bumps Every N Years" and bump_frequency > 0:
        bumps_already_fired = years_elapsed // bump_frequency
    else:
        bumps_already_fired = 0

    for year in range(1, years + 1):
        # Years from original lease commencement at this point in the hold
        years_from_original_start = years_elapsed + year

        # Determine lease status
        if year > current_term_remaining:
            years_into_renewal = year - current_term_remaining
            lease_status = f"Renewal Year {years_into_renewal}"
        else:
            lease_status = "Current Term"

        # Calculate NOI
        if rent_structure_type == "Fixed Bumps Every N Years" and bump_frequency > 0:
            # Total bumps that have fired by this point on the original timeline
            total_bumps_at_this_point = (years_from_original_start - 1) // bump_frequency
            # Only the bumps BEYOND what already fired at acquisition matter
            incremental_bumps = total_bumps_at_this_point - bumps_already_fired
            noi = base_rent * ((1 + bump_pct / 100) ** incremental_bumps)
        elif rent_structure_type == "Annual Escalator (%)":
            # Year 1 = base_rent, each subsequent year compounds from there
            noi = base_rent * ((1 + annual_escalator / 100) ** (year - 1))
        else:  # Flat
            noi = base_rent

        years_remaining_on_lease = max(0, current_term_remaining - year)

        noi_schedule.append({
            'Year': year,
            'NOI': noi,
            'Lease Status': lease_status,
            'Years Remaining (Current Term)': years_remaining_on_lease
        })

    return pd.DataFrame(noi_schedule)

def calculate_total_project_cost(purchase_price, closing_costs_pct, bridge_orig_points, acquisition_fee_pct, bridge_loan_amount):
    """Calculate total uses of funds"""
    closing_costs = purchase_price * (closing_costs_pct / 100)
    bridge_origination = bridge_loan_amount * (bridge_orig_points / 100)
    acquisition_fee = purchase_price * (acquisition_fee_pct / 100)

    total_uses = purchase_price + closing_costs + bridge_origination + acquisition_fee

    return {
        'purchase_price': purchase_price,
        'closing_costs': closing_costs,
        'bridge_origination': bridge_origination,
        'acquisition_fee': acquisition_fee,
        'total_uses': total_uses
    }

def calculate_sources(purchase_price, bridge_ltv, lp_equity, gp_equity, closing_costs_pct, bridge_orig_points, acquisition_fee_pct):
    """Calculate sources and uses"""
    bridge_loan = purchase_price * (bridge_ltv / 100)

    costs = calculate_total_project_cost(
        purchase_price,
        closing_costs_pct,
        bridge_orig_points,
        acquisition_fee_pct,
        bridge_loan
    )

    total_equity_needed = costs['total_uses'] - bridge_loan

    return {
        'bridge_loan': bridge_loan,
        'lp_equity': lp_equity,
        'gp_equity': gp_equity,
        'total_equity': lp_equity + gp_equity,
        'total_sources': bridge_loan + lp_equity + gp_equity,
        'equity_needed': total_equity_needed,
        'uses': costs
    }

def calculate_multi_tenant_noi(tenants_list, holding_period):
    """
    Calculate aggregate NOI projection for multi-tenant property.

    Parameters:
    - tenants_list: list of tenant dicts with lease terms and escalations
    - holding_period: number of years to project

    Returns: DataFrame with Year, NOI, Lease Status columns
    """
    noi_schedule = []

    for year in range(1, holding_period + 1):
        total_rent = 0
        lease_statuses = []

        for tenant in tenants_list:
            if tenant['status'] == 'Vacant':
                lease_statuses.append(f"{tenant['name']}: Vacant")
                continue

            # Check if tenant lease has expired
            if year > tenant['lease_expiration_year']:
                # Check if renewal options are available
                years_past_expiration = year - tenant['lease_expiration_year']
                option_number = (years_past_expiration - 1) // tenant['option_term'] + 1

                if option_number <= tenant['renewal_options']:
                    # In renewal option period
                    lease_statuses.append(f"{tenant['name']}: Option {option_number}")
                else:
                    # No more options, lease expired
                    lease_statuses.append(f"{tenant['name']}: EXPIRED")
                    continue
            else:
                lease_statuses.append(f"{tenant['name']}: Active")

            # Calculate rent for this year based on escalation
            base_rent = tenant['annual_rent']
            escalation_type = tenant['escalation_type']

            # Calculate years since lease start for escalation
            years_since_start = tenant['years_elapsed'] + year - 1

            if escalation_type == "Fixed Bumps Every N Years":
                bump_freq = tenant['bump_frequency']
                bump_pct = tenant['bump_percentage']
                if bump_freq > 0:
                    num_bumps = years_since_start // bump_freq
                    current_rent = base_rent * ((1 + bump_pct/100) ** num_bumps)
                else:
                    current_rent = base_rent
            elif escalation_type == "Annual Escalator (%)":
                ann_esc = tenant['annual_escalator']
                current_rent = base_rent * ((1 + ann_esc/100) ** years_since_start)
            else:  # Flat
                current_rent = base_rent

            total_rent += current_rent

        noi_schedule.append({
            'Year': year,
            'NOI': total_rent,
            'Lease Status': " | ".join(lease_statuses) if lease_statuses else "All Vacant"
        })

    return pd.DataFrame(noi_schedule)
