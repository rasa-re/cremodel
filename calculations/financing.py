import numpy as np

def calculate_bridge_loan_payment(loan_amount, annual_rate, term_years, is_io):
    """Calculate annual debt service for bridge loan"""
    if is_io:
        # Interest only
        return loan_amount * (annual_rate / 100)
    else:
        # Amortizing
        monthly_rate = (annual_rate / 100) / 12
        num_payments = term_years * 12
        if monthly_rate == 0:
            monthly_payment = loan_amount / num_payments
        else:
            monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
        return monthly_payment * 12

def calculate_bridge_loan_balance(loan_amount, annual_rate, term_years, year, is_io):
    """Calculate remaining balance of bridge loan at end of specific year"""
    if is_io:
        # IO loan - balance doesn't change
        return loan_amount
    else:
        # Amortizing loan
        monthly_rate = (annual_rate / 100) / 12
        num_payments_made = year * 12
        total_payments = term_years * 12

        if monthly_rate == 0:
            return loan_amount - (loan_amount / total_payments * num_payments_made)

        remaining_payments = total_payments - num_payments_made
        monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**total_payments) / ((1 + monthly_rate)**total_payments - 1)

        if remaining_payments <= 0:
            return 0

        remaining_balance = monthly_payment * ((1 + monthly_rate)**remaining_payments - 1) / (monthly_rate * (1 + monthly_rate)**remaining_payments)
        return remaining_balance

def calculate_dscr(noi, annual_debt_service):
    """Calculate Debt Service Coverage Ratio"""
    if annual_debt_service == 0:
        return float('inf')
    return noi / annual_debt_service

def calculate_debt_yield(noi, loan_balance):
    """Calculate Debt Yield"""
    if loan_balance == 0:
        return 0
    return (noi / loan_balance) * 100

def calculate_ltv(loan_balance, property_value):
    """Calculate Loan-to-Value ratio"""
    if property_value == 0:
        return 0
    return (loan_balance / property_value) * 100

def calculate_perm_loan_payment(loan_amount, annual_rate, amort_years):
    """Calculate annual debt service for permanent loan"""
    monthly_rate = (annual_rate / 100) / 12
    num_payments = amort_years * 12

    if monthly_rate == 0:
        monthly_payment = loan_amount / num_payments
    else:
        monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)

    return monthly_payment * 12

def calculate_perm_loan_balance(loan_amount, annual_rate, amort_years, year):
    """Calculate remaining balance of perm loan at end of specific year"""
    monthly_rate = (annual_rate / 100) / 12
    total_payments = amort_years * 12
    num_payments_made = year * 12

    if monthly_rate == 0:
        return loan_amount - (loan_amount / total_payments * num_payments_made)

    remaining_payments = total_payments - num_payments_made

    if remaining_payments <= 0:
        return 0

    monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**total_payments) / ((1 + monthly_rate)**total_payments - 1)
    remaining_balance = monthly_payment * ((1 + monthly_rate)**remaining_payments - 1) / (monthly_rate * (1 + monthly_rate)**remaining_payments)

    return remaining_balance

def calculate_max_loan_by_dscr(noi, annual_rate, amort_years, target_dscr):
    """Calculate maximum loan amount based on DSCR constraint"""
    max_debt_service = noi / target_dscr

    # Back into loan amount from payment
    monthly_rate = (annual_rate / 100) / 12
    num_payments = amort_years * 12
    monthly_payment = max_debt_service / 12

    if monthly_rate == 0:
        return monthly_payment * num_payments

    max_loan = monthly_payment * ((1 + monthly_rate)**num_payments - 1) / (monthly_rate * (1 + monthly_rate)**num_payments)
    return max_loan

def calculate_max_loan_by_ltv(property_value, target_ltv):
    """Calculate maximum loan amount based on LTV constraint"""
    return property_value * (target_ltv / 100)

def calculate_loan_from_payment(annual_payment, annual_rate, amort_years):
    """Back into loan amount from payment amount"""
    monthly_payment = annual_payment / 12
    monthly_rate = (annual_rate / 100) / 12
    num_payments = amort_years * 12

    if monthly_rate == 0:
        return monthly_payment * num_payments

    loan_amount = monthly_payment * ((1 + monthly_rate)**num_payments - 1) / (monthly_rate * (1 + monthly_rate)**num_payments)
    return loan_amount

def calculate_refinance(noi_at_refi, refi_valuation_method, refi_cap_rate,
                       fixed_refi_value, purchase_price, years_to_refi, appreciation_rate,
                       perm_rate, perm_ltv, perm_amort, target_dscr,
                       use_conservative, allow_cashout, max_cashout_pct,
                       bridge_balance, bridge_prepay_penalty_pct,
                       perm_orig_points, refi_legal_costs):
    """
    Calculate refinance with proper property valuation
    """

    # Step 1: Determine property value at refinance
    if refi_valuation_method == "Based on Cap Rate":
        property_value = noi_at_refi / (refi_cap_rate / 100)
        valuation_method_used = f"NOI ${noi_at_refi:,.0f} / {refi_cap_rate}% cap = ${property_value:,.0f}"

    elif refi_valuation_method == "Fixed Property Value":
        property_value = fixed_refi_value
        valuation_method_used = f"Appraised Value: ${property_value:,.0f}"

    else:  # Based on Original Purchase Price
        property_value = purchase_price * ((1 + appreciation_rate/100) ** years_to_refi)
        valuation_method_used = f"Purchase ${purchase_price:,.0f} × (1+{appreciation_rate}%)^{years_to_refi} = ${property_value:,.0f}"

    # Step 2: Calculate maximum loan by LTV constraint
    max_loan_by_ltv = property_value * (perm_ltv / 100)

    # Step 3: Calculate maximum loan by DSCR constraint
    max_debt_service_by_dscr = noi_at_refi / target_dscr
    max_loan_by_dscr = calculate_loan_from_payment(
        max_debt_service_by_dscr, perm_rate, perm_amort
    )

    # Step 4: Determine which constraint binds
    if use_conservative:
        new_loan_amount = min(max_loan_by_ltv, max_loan_by_dscr)
        binding_constraint = 'LTV' if max_loan_by_ltv < max_loan_by_dscr else 'DSCR'
    else:
        new_loan_amount = max(max_loan_by_ltv, max_loan_by_dscr)
        binding_constraint = 'LTV' if max_loan_by_ltv > max_loan_by_dscr else 'DSCR'

    # Step 5: Calculate refinance costs
    prepayment_penalty = bridge_balance * (bridge_prepay_penalty_pct / 100)
    perm_origination = new_loan_amount * (perm_orig_points / 100)
    total_refi_costs = prepayment_penalty + perm_origination + refi_legal_costs

    # Step 6: Calculate proceeds
    gross_proceeds = new_loan_amount
    bridge_payoff = bridge_balance
    net_proceeds_before_cashout_limit = gross_proceeds - bridge_payoff - total_refi_costs

    # Step 7: Apply cash-out limits if applicable
    if not allow_cashout and net_proceeds_before_cashout_limit > 0:
        # Can't take cash out - loan can only pay off bridge
        new_loan_amount = bridge_balance + total_refi_costs
        net_proceeds = 0
        cashout_limited = True
        cashout_explanation = "Cash-out not allowed - loan sized to cover bridge payoff + costs only"

    elif allow_cashout and net_proceeds_before_cashout_limit > 0:
        # Check cash-out limits
        equity_gained = property_value - purchase_price
        max_cashout_allowed = equity_gained * (max_cashout_pct / 100)

        if net_proceeds_before_cashout_limit > max_cashout_allowed:
            # Reduce loan to max cash-out limit
            new_loan_amount = bridge_balance + total_refi_costs + max_cashout_allowed
            net_proceeds = max_cashout_allowed
            cashout_limited = True
            cashout_explanation = f"Cash-out limited to {max_cashout_pct}% of equity gained (${max_cashout_allowed:,.0f})"
        else:
            net_proceeds = net_proceeds_before_cashout_limit
            cashout_limited = False
            cashout_explanation = "Full proceeds available"
    else:
        # Negative proceeds - need to pay down
        net_proceeds = net_proceeds_before_cashout_limit
        cashout_limited = False
        cashout_explanation = "Cash required to pay down loan" if net_proceeds < 0 else "Break-even refi"

    # Step 8: Calculate final debt service
    final_debt_service = calculate_perm_loan_payment(new_loan_amount, perm_rate, perm_amort)
    final_dscr = noi_at_refi / final_debt_service if final_debt_service > 0 else float('inf')
    final_ltv = (new_loan_amount / property_value) * 100 if property_value > 0 else 0

    return {
        'property_value': property_value,
        'valuation_method': valuation_method_used,
        'noi_at_refi': noi_at_refi,
        'refi_cap_rate': refi_cap_rate if refi_valuation_method == "Based on Cap Rate" else None,

        'max_loan_by_ltv': max_loan_by_ltv,
        'max_loan_by_dscr': max_loan_by_dscr,
        'binding_constraint': binding_constraint,

        'new_loan_amount': new_loan_amount,
        'bridge_payoff': bridge_payoff,
        'prepayment_penalty': prepayment_penalty,
        'perm_origination': perm_origination,
        'refi_legal_costs': refi_legal_costs,
        'total_refi_costs': total_refi_costs,

        'gross_proceeds': new_loan_amount,
        'net_proceeds': net_proceeds,
        'cashout_limited': cashout_limited,
        'cashout_explanation': cashout_explanation,

        'final_debt_service': final_debt_service,
        'final_dscr': final_dscr,
        'final_ltv': final_ltv,

        'equity_before_refi': property_value - bridge_balance,
        'equity_after_refi': property_value - new_loan_amount,

        # Keep old fields for backward compatibility
        'max_by_dscr': max_loan_by_dscr,
        'max_by_ltv': max_loan_by_ltv
    }

def check_refi_feasibility_with_lease(current_term_remaining, options_remaining,
                                     option_term, refi_year, min_term_required=7):
    """Check if refi is feasible considering lease term and renewal options"""

    years_at_refi_current = current_term_remaining - refi_year
    years_at_refi_with_options = years_at_refi_current + (options_remaining * option_term)

    if years_at_refi_current >= min_term_required:
        return {
            'feasible': True,
            'status': '✅ Feasible with current term',
            'requirement': None
        }
    elif years_at_refi_with_options >= min_term_required and options_remaining > 0:
        return {
            'feasible': True,
            'status': '⚠️ Requires tenant to exercise renewal option',
            'requirement': f'Must secure renewal commitment before Year {refi_year}',
            'years_at_refi': years_at_refi_with_options
        }
    else:
        return {
            'feasible': False,
            'status': '❌ Not feasible - insufficient lease term',
            'requirement': 'Cannot refinance - consider bridge loan only'
        }
