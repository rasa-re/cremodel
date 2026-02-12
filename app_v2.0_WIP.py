import streamlit as st
import pandas as pd
import numpy as np
import json, os, glob as glob_mod
from calculations.cash_flows import (calculate_sources, calculate_noi_projection_with_lease, calculate_multi_tenant_noi)
from calculations.financing import (calculate_bridge_loan_payment, calculate_bridge_loan_balance, calculate_dscr,
                                   calculate_perm_loan_payment, calculate_perm_loan_balance, calculate_refinance,
                                   check_refi_feasibility_with_lease)
from calculations.distributions import (calculate_multi_year_waterfall)

# --- Scenario persistence helpers ---
SCENARIOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios")
os.makedirs(SCENARIOS_DIR, exist_ok=True)

SCENARIO_KEYS = [
    "deal_strategy", "property_name", "property_address", "property_city_state",
    "tenant_name", "property_type", "property_sqft", "year_built",
    "purchase_price", "exit_strategy", "holding_period",
    "refi_year_buyhold", "continue_after_refi", "additional_years",
    "tenants",  # Multi-tenant list
    "current_term_remaining_input", "years_elapsed",
    "num_renewal_options", "option_term_years",
    "base_annual_rent", "rent_structure_type",
    "bump_frequency", "bump_percentage", "annual_escalator",
    "renegotiate_lease", "renego_year", "renego_rent", "renego_structure",
    "renego_bump_freq", "renego_bump_pct", "renego_escalator", "renego_new_term",
    "closing_costs_pct", "bridge_orig_points", "perm_orig_points_acq", "acquisition_fee_pct",
    "bridge_ltv", "bridge_rate", "bridge_term", "bridge_io", "bridge_prepay_penalty",
    "value_add_capex", "value_add_year",
    "refi_year", "perm_rate", "perm_amort", "perm_orig_points", "refi_legal_costs",
    "refi_valuation_method", "refi_cap_rate", "fixed_refi_value", "appreciation_rate",
    "perm_ltv", "target_dscr", "use_conservative",
    "allow_cashout", "max_cashout_pct",
    "capex_reserve", "asset_mgmt_pct", "admin_costs",
    "lp_equity_pct", "pref_rate", "gp_profit_share", "include_catchup",
    "promote_mode", "promote_hurdle_irr", "gp_promote_share", "lp_irr_cap",
    "exit_cap_rate", "broker_commission_pct", "exit_legal_pct", "disposition_fee_pct",
    "deal_name",
]

def _list_scenarios():
    return sorted([os.path.splitext(os.path.basename(f))[0]
                   for f in glob_mod.glob(os.path.join(SCENARIOS_DIR, "*.json"))])

def _save_scenario(name):
    data = {k: st.session_state.get(k) for k in SCENARIO_KEYS if k in st.session_state}
    path = os.path.join(SCENARIOS_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

def _load_scenario(name):
    path = os.path.join(SCENARIOS_DIR, f"{name}.json")
    with open(path) as f:
        data = json.load(f)
    for k, v in data.items():
        st.session_state[k] = v

# Page configuration
st.set_page_config(
    page_title="CRE Underwriting Model",
    page_icon="🏢",
    layout="wide"
)

st.title("🏢 Commercial Real Estate Underwriting Model")
st.markdown("**Net Lease Property Analysis with Investor Waterfall**")
st.caption("Version 2.0 (Multi-Tenant) - Work in Progress")

# SIDEBAR INPUTS
st.sidebar.title("Deal Inputs")

# --- Save / Load Scenario ---
with st.sidebar.expander("💾 Scenarios", expanded=False):
    scenarios = _list_scenarios()
    if scenarios:
        load_pick = st.selectbox("Load scenario", options=["—"] + scenarios, key="__load_pick__")
        if load_pick != "—":
            col_lb, col_db = st.columns(2)
            if col_lb.button("Load", key="__load_btn__", use_container_width=True):
                _load_scenario(load_pick)
                st.rerun()
            if col_db.button("Delete", key="__del_btn__", use_container_width=True):
                os.remove(os.path.join(SCENARIOS_DIR, f"{load_pick}.json"))
                st.rerun()
    else:
        st.caption("No saved scenarios yet")
    st.markdown("---")
    save_name = st.text_input("Save as", placeholder="scenario name", key="__save_name__")
    if st.button("Save current inputs", key="__save_btn__", disabled=not save_name.strip(), use_container_width=True):
        _save_scenario(save_name.strip())
        st.success(f"Saved: {save_name.strip()}")
    st.markdown("---")
    uploaded = st.file_uploader("Upload scenario (.json)", type="json", key="__upload__", label_visibility="visible")
    if uploaded is not None:
        if st.button("Load uploaded file", key="__upload_load_btn__", use_container_width=True):
            try:
                data = json.loads(uploaded.getvalue().decode("utf-8"))
                for k, v in data.items():
                    st.session_state[k] = v
                st.rerun()
            except Exception as e:
                st.error(f"Could not load file: {e}")

# Section 0: Deal Strategy
with st.sidebar.expander("🎯 Deal Strategy", expanded=True):
    deal_strategy = st.radio(
        "Deal Structure:",
        options=[
            "Buy-and-Hold with Permanent Financing",
            "Bridge-to-Permanent (Value-Add)"
        ],
        index=0,
        key="deal_strategy"
    )

    if deal_strategy == "Buy-and-Hold with Permanent Financing":
        st.info("**Standard stabilized asset**\n• Permanent loan at acquisition\n• Hold for cash flow\n• Exit via sale or refi")
    else:
        st.info("**Value-add strategy**\n• Bridge loan at acquisition\n• Stabilize property (lease renewal, etc.)\n• Refinance to permanent\n• Exit decision after refi")

# Section 0b: Property Details (for PDF / deal identification)
with st.sidebar.expander("📍 Property Details"):
    property_name = st.text_input("Property Name", "", key="property_name")
    property_address = st.text_input("Street Address", "", key="property_address")
    property_city_state = st.text_input("City, State, ZIP", "", key="property_city_state")
    tenant_name = st.text_input("Tenant Name", "", key="tenant_name")
    property_type = st.selectbox("Property Type", [
        "Single-Tenant Retail",
        "Single-Tenant Office",
        "Single-Tenant Industrial",
        "Single-Tenant Healthcare",
        "Single-Tenant Restaurant",
        "Other"
    ], index=0, key="property_type")
    property_sqft = st.number_input("Square Footage", value=0, step=100, key="property_sqft")
    year_built = st.number_input("Year Built", value=2000, min_value=1900, max_value=2026, step=1, key="year_built")

# Section 1: Property Assumptions
with st.sidebar.expander("🏠 Deal Assumptions", expanded=True):
    purchase_price = st.number_input("Purchase Price ($)", value=5000000, step=100000, key="purchase_price")
    if deal_strategy == "Buy-and-Hold with Permanent Financing":
        exit_strategy = st.radio("Exit Strategy:", ["Sell Property", "Cash-Out Refinance"], key="exit_strategy")
        if exit_strategy == "Sell Property":
            holding_period = st.selectbox("Exit Year", options=[3, 5, 7, 10], index=1, key="holding_period")
        else:
            refi_year_buyhold = st.selectbox("Refinance in Year", options=[1, 2, 3, 4, 5], index=2, key="refi_year_buyhold")
            continue_after_refi = st.checkbox("Hold After Refi?", value=True, key="continue_after_refi")
            if continue_after_refi:
                additional_years = st.number_input("Additional Years After Refi", value=5, min_value=1, max_value=20, key="additional_years")
                holding_period = refi_year_buyhold + additional_years
            else:
                holding_period = refi_year_buyhold
    else:
        # Bridge-to-perm strategy
        holding_period = st.selectbox("Total Hold Period (years)", options=[3, 5, 7, 10], index=1, key="holding_period")

# Section 1b: Multi-Tenant Structure
with st.sidebar.expander("🏢 Tenants", expanded=True):
    # Initialize tenant list in session state
    if 'tenants' not in st.session_state:
        st.session_state['tenants'] = [
            {
                'id': 0,
                'name': 'Tenant 1',
                'sqft': 10000,
                'annual_rent': 250000,
                'lease_expiration_year': 7,
                'years_elapsed': 8,
                'renewal_options': 3,
                'option_term': 5,
                'escalation_type': 'Fixed Bumps Every N Years',
                'bump_frequency': 5,
                'bump_percentage': 10.0,
                'annual_escalator': 0.0,
                'status': 'Occupied'
            }
        ]

    # Buttons to add/remove tenants
    col1, col2 = st.columns(2)
    if col1.button("➕ Add Tenant", use_container_width=True):
        new_id = max([t['id'] for t in st.session_state['tenants']]) + 1 if st.session_state['tenants'] else 0
        st.session_state['tenants'].append({
            'id': new_id,
            'name': f'Tenant {new_id + 1}',
            'sqft': 5000,
            'annual_rent': 100000,
            'lease_expiration_year': 5,
            'years_elapsed': 0,
            'renewal_options': 2,
            'option_term': 5,
            'escalation_type': 'Fixed Bumps Every N Years',
            'bump_frequency': 5,
            'bump_percentage': 10.0,
            'annual_escalator': 0.0,
            'status': 'Occupied'
        })
        st.rerun()

    if col2.button("➖ Remove Last", use_container_width=True, disabled=len(st.session_state['tenants']) <= 1):
        st.session_state['tenants'].pop()
        st.rerun()

    st.markdown("---")

    # Display each tenant's inputs
    for i, tenant in enumerate(st.session_state['tenants']):
        with st.expander(f"📋 {tenant['name']}", expanded=(i == 0)):
            tenant['name'] = st.text_input("Tenant Name", value=tenant['name'], key=f"tenant_name_{tenant['id']}")
            tenant['status'] = st.selectbox("Status", options=['Occupied', 'Vacant'], index=0 if tenant['status'] == 'Occupied' else 1, key=f"tenant_status_{tenant['id']}")

            if tenant['status'] == 'Occupied':
                tenant['sqft'] = st.number_input("Square Footage", value=tenant['sqft'], step=100, min_value=0, key=f"tenant_sqft_{tenant['id']}")
                tenant['annual_rent'] = st.number_input("Annual Rent ($)", value=tenant['annual_rent'], step=10000, min_value=0, key=f"tenant_rent_{tenant['id']}")

                st.markdown("**Lease Terms**")
                tenant['lease_expiration_year'] = st.number_input("Years Until Lease Expires", value=tenant['lease_expiration_year'], min_value=0, max_value=30, step=1, key=f"tenant_exp_{tenant['id']}")
                tenant['years_elapsed'] = st.number_input("Years Into Current Lease", value=tenant['years_elapsed'], min_value=0, max_value=30, step=1, key=f"tenant_elapsed_{tenant['id']}")
                tenant['renewal_options'] = st.number_input("Renewal Options", value=tenant['renewal_options'], min_value=0, max_value=5, step=1, key=f"tenant_renewals_{tenant['id']}")
                tenant['option_term'] = st.number_input("Option Term (years)", value=tenant['option_term'], min_value=1, max_value=10, step=1, key=f"tenant_opt_term_{tenant['id']}")

                st.markdown("**Rent Escalation**")
                tenant['escalation_type'] = st.selectbox("Escalation Type", options=[
                    "Fixed Bumps Every N Years",
                    "Annual Escalator (%)",
                    "Flat (No Increases)"
                ], index=['Fixed Bumps Every N Years', 'Annual Escalator (%)', 'Flat (No Increases)'].index(tenant['escalation_type']), key=f"tenant_esc_type_{tenant['id']}")

                if tenant['escalation_type'] == "Fixed Bumps Every N Years":
                    tenant['bump_frequency'] = st.number_input("Bump Every (years)", value=tenant['bump_frequency'], min_value=1, max_value=10, step=1, key=f"tenant_bump_freq_{tenant['id']}")
                    tenant['bump_percentage'] = st.number_input("Bump Amount (%)", value=tenant['bump_percentage'], min_value=0.0, step=0.5, key=f"tenant_bump_pct_{tenant['id']}")
                    tenant['annual_escalator'] = 0.0
                elif tenant['escalation_type'] == "Annual Escalator (%)":
                    tenant['annual_escalator'] = st.number_input("Annual Increase (%)", value=tenant.get('annual_escalator', 1.5), min_value=0.0, step=0.1, key=f"tenant_ann_esc_{tenant['id']}")
                    tenant['bump_frequency'] = 0
                    tenant['bump_percentage'] = 0.0
                else:
                    tenant['bump_frequency'] = 0
                    tenant['bump_percentage'] = 0.0
                    tenant['annual_escalator'] = 0.0
            else:
                # Vacant tenant
                tenant['sqft'] = st.number_input("Square Footage", value=tenant['sqft'], step=100, min_value=0, key=f"tenant_sqft_{tenant['id']}")
                tenant['annual_rent'] = 0
                tenant['lease_expiration_year'] = 0
                tenant['years_elapsed'] = 0
                tenant['renewal_options'] = 0
                tenant['option_term'] = 0
                tenant['bump_frequency'] = 0
                tenant['bump_percentage'] = 0.0
                tenant['annual_escalator'] = 0.0

# Store aggregated values for backward compatibility with existing calculations
# (We'll update the NOI calculation to use the tenant list directly)
base_annual_rent = sum([t['annual_rent'] for t in st.session_state['tenants']])
property_sqft = sum([t['sqft'] for t in st.session_state['tenants']])
# For single-tenant compatibility, use first tenant's lease terms
if st.session_state['tenants']:
    first_tenant = st.session_state['tenants'][0]
    current_term_remaining_input = first_tenant['lease_expiration_year']
    years_elapsed = first_tenant['years_elapsed']
    num_renewal_options = first_tenant['renewal_options']
    option_term_years = first_tenant['option_term']
    rent_structure_type = first_tenant['escalation_type']
    bump_frequency = first_tenant['bump_frequency']
    bump_percentage = first_tenant['bump_percentage']
    annual_escalator = first_tenant['annual_escalator']
else:
    current_term_remaining_input = 0
    years_elapsed = 0
    num_renewal_options = 0
    option_term_years = 5
    rent_structure_type = "Flat (No Increases)"
    bump_frequency = 0
    bump_percentage = 0.0
    annual_escalator = 0.0

# Remove lease renegotiation for now in multi-tenant (can add per-tenant renegotiation later)
renegotiate_lease = False
renego_year = 999
renego_rent = base_annual_rent
renego_structure = rent_structure_type
renego_bump_freq = bump_frequency
renego_bump_pct = bump_percentage
renego_escalator = annual_escalator
renego_new_term = 0

# Section 2: Acquisition Costs
with st.sidebar.expander("💰 Acquisition Costs"):
    closing_costs_pct = st.number_input("Closing Costs (% of purchase)", value=1.5, step=0.1, key="closing_costs_pct")
    if deal_strategy == "Bridge-to-Permanent (Value-Add)":
        bridge_orig_points = st.number_input("Bridge Loan Origination (points)", value=1.5, step=0.1, key="bridge_orig_points")
    else:
        perm_orig_points_acq = st.number_input("Perm Loan Origination (points)", value=1.5, step=0.1, key="perm_orig_points_acq")
    acquisition_fee_pct = st.number_input("Acquisition Fee to GP (% of purchase)", value=1.5, step=0.1, key="acquisition_fee_pct")

# Section 2b: Capital Expenditures
with st.sidebar.expander("🔧 Capital Expenditures"):
    value_add_capex = st.number_input("CapEx Amount ($)", value=0, step=25000, key="value_add_capex")
    value_add_year = st.number_input("Spend in Year", value=1, min_value=1, max_value=10, step=1, key="value_add_year")
    st.caption("Added to equity raise at close; spent in the selected year")

# Section 3: Bridge Financing (only for value-add strategy)
if deal_strategy == "Bridge-to-Permanent (Value-Add)":
    with st.sidebar.expander("🏦 Bridge Financing"):
        bridge_ltv = st.number_input("Bridge Loan LTV (%)", value=75.0, step=1.0, max_value=100.0, key="bridge_ltv")
        bridge_rate = st.number_input("Bridge Interest Rate (%)", value=7.0, step=0.1, key="bridge_rate")
        bridge_term = st.number_input("Bridge Term (years)", value=2, step=1, min_value=1, max_value=5, key="bridge_term")
        bridge_io = st.checkbox("Interest Only?", value=True, key="bridge_io")
        bridge_prepay_penalty = st.number_input("Prepayment Penalty (%)", value=2.0, step=0.1, key="bridge_prepay_penalty")
else:
    # Default values for buy-and-hold (won't use bridge loan)
    # Read from session_state to preserve values if user switches between strategies
    bridge_ltv = st.session_state.get('bridge_ltv', 0)
    bridge_rate = st.session_state.get('bridge_rate', 0)
    bridge_term = st.session_state.get('bridge_term', 0)
    bridge_io = st.session_state.get('bridge_io', True)
    bridge_prepay_penalty = st.session_state.get('bridge_prepay_penalty', 0)
    bridge_orig_points = st.session_state.get('bridge_orig_points', 0)

# Section 4: Permanent Financing
with st.sidebar.expander("🏛️ Permanent Financing"):
    if deal_strategy == "Bridge-to-Permanent (Value-Add)":
        # For value-add, this is about the refinance
        st.markdown("**Refinance Timing**")
        refi_year = st.selectbox("Refinance in Year", options=[1, 2, 3, 4, 5], index=1, key="refi_year")
    else:
        # For buy-and-hold, permanent loan is at acquisition
        st.markdown("**Permanent Loan at Acquisition**")

    perm_rate = st.number_input("Permanent Interest Rate (%)", value=6.0, step=0.1, key="perm_rate")
    perm_amort = st.number_input("Amortization Period (years)", value=25, step=1, key="perm_amort")

    if deal_strategy == "Bridge-to-Permanent (Value-Add)":
        perm_orig_points = st.number_input("Perm Loan Origination (points)", value=1.5, step=0.1, key="perm_orig_points")
        refi_legal_costs = st.number_input("Appraisal/Legal/Fees ($)", value=25000, step=1000, key="refi_legal_costs")

        st.markdown("**Permanent Loan Sizing**")
        refi_valuation_method = st.selectbox("Refinance Valuation Method", options=[
            "Based on Cap Rate",
            "Fixed Property Value",
            "Based on Original Purchase Price"
        ], index=0, key="refi_valuation_method")

        if refi_valuation_method == "Based on Cap Rate":
            refi_cap_rate = st.number_input("Refinance Cap Rate (%)", value=6.5, step=0.1, key="refi_cap_rate")
            st.caption("Lender will value property at NOI / Cap Rate")
            fixed_refi_value = st.session_state.get('fixed_refi_value', 0)
            appreciation_rate = st.session_state.get('appreciation_rate', 0)
        elif refi_valuation_method == "Fixed Property Value":
            fixed_refi_value = st.number_input("Property Value at Refi ($)", value=5500000, step=100000, key="fixed_refi_value")
            st.caption("Enter appraised value")
            refi_cap_rate = st.session_state.get('refi_cap_rate', 0)
            appreciation_rate = st.session_state.get('appreciation_rate', 0)
        else:  # Based on Original Purchase Price
            appreciation_rate = st.number_input("Appreciation Rate (% per year)", value=3.0, step=0.5, key="appreciation_rate")
            st.caption("Calculates: Value = Purchase Price × (1 + rate)^years")
            refi_cap_rate = st.session_state.get('refi_cap_rate', 0)
            fixed_refi_value = st.session_state.get('fixed_refi_value', 0)

        st.markdown("**Permanent Loan Constraints**")
        perm_ltv = st.number_input("Permanent LTV Target (%)", value=75.0, step=1.0, max_value=100.0, key="perm_ltv")
        target_dscr = st.number_input("Target DSCR", value=1.25, step=0.01, key="target_dscr")
        use_conservative = st.checkbox("Use More Conservative of LTV/DSCR?", value=True, key="use_conservative")
        st.caption("Lender will use whichever gives lower loan amount")

        st.markdown("**Cash-Out Rules**")
        allow_cashout = st.checkbox("Allow Cash-Out Refinance?", value=True, key="allow_cashout")
        if allow_cashout:
            max_cashout_pct = st.number_input("Maximum Cash-Out (% of equity gained)", value=80.0, step=5.0, max_value=100.0, key="max_cashout_pct")
            st.caption("Lenders typically limit cash-out to 80% of equity gained")
        else:
            max_cashout_pct = st.session_state.get('max_cashout_pct', 0)
            st.caption("Refi will be used only to pay off bridge loan")
    else:
        # Buy-and-hold: permanent loan at acquisition
        perm_ltv = st.number_input("Permanent LTV (%)", value=75.0, step=1.0, max_value=100.0, key="perm_ltv")
        target_dscr = st.number_input("Minimum DSCR", value=1.25, step=0.01, key="target_dscr")
        use_conservative = st.checkbox("Use More Conservative of LTV/DSCR?", value=True, key="use_conservative")
        st.caption("Lender will use whichever gives lower loan amount")

        # For buy-and-hold, if they're doing a cash-out refi later
        if 'exit_strategy' in locals() and exit_strategy == "Cash-Out Refinance":
            st.markdown("**Future Refinance Parameters**")
            refi_year = refi_year_buyhold
            perm_orig_points = st.number_input("Future Refi Origination (points)", value=1.5, step=0.1, key="perm_orig_points")
            refi_legal_costs = st.number_input("Future Refi Legal/Fees ($)", value=25000, step=1000, key="refi_legal_costs")

            refi_valuation_method = st.selectbox("Future Refinance Valuation", options=[
                "Based on Cap Rate",
                "Fixed Property Value",
                "Based on Original Purchase Price"
            ], index=0, key="refi_valuation_method")

            if refi_valuation_method == "Based on Cap Rate":
                refi_cap_rate = st.number_input("Future Refi Cap Rate (%)", value=6.5, step=0.1, key="refi_cap_rate")
                fixed_refi_value = 0
                appreciation_rate = 0
            elif refi_valuation_method == "Fixed Property Value":
                fixed_refi_value = st.number_input("Future Property Value ($)", value=5500000, step=100000, key="fixed_refi_value")
                refi_cap_rate = 0
                appreciation_rate = 0
            else:
                appreciation_rate = st.number_input("Appreciation Rate (% per year)", value=3.0, step=0.5, key="appreciation_rate")
                refi_cap_rate = 0
                fixed_refi_value = 0

            allow_cashout = st.checkbox("Allow Cash-Out?", value=True, key="allow_cashout")
            if allow_cashout:
                max_cashout_pct = st.number_input("Max Cash-Out (% of equity gained)", value=80.0, step=5.0, max_value=100.0, key="max_cashout_pct")
            else:
                max_cashout_pct = st.session_state.get('max_cashout_pct', 0)
        else:
            # No refi planned - read from session_state to preserve values
            refi_year = 999  # Never
            perm_orig_points = st.session_state.get('perm_orig_points', 0)
            refi_legal_costs = st.session_state.get('refi_legal_costs', 0)
            refi_valuation_method = st.session_state.get('refi_valuation_method', "Based on Cap Rate")
            refi_cap_rate = st.session_state.get('refi_cap_rate', 6.5)
            fixed_refi_value = st.session_state.get('fixed_refi_value', 0)
            appreciation_rate = st.session_state.get('appreciation_rate', 0)
            allow_cashout = st.session_state.get('allow_cashout', False)
            max_cashout_pct = st.session_state.get('max_cashout_pct', 0)

# Section 5: Non-Operating Expenses
with st.sidebar.expander("⚙️ Non-Operating Expenses"):
    capex_reserve = st.number_input("Annual CapEx Reserve ($)", value=10000, step=1000, key="capex_reserve")
    asset_mgmt_pct = st.number_input("Asset Management Fee (% of LP equity)", value=1.5, step=0.1, key="asset_mgmt_pct")
    admin_costs = st.number_input("Annual Admin/Accounting ($)", value=5000, step=500, key="admin_costs")

# Section 6: Investor Structure
with st.sidebar.expander("👥 Investor Structure"):
    lp_equity_pct = st.number_input("LP Equity (%)", value=80.0, min_value=0.0, max_value=100.0, step=1.0, key="lp_equity_pct")
    gp_equity_pct = 100.0 - lp_equity_pct
    st.caption(f"GP Equity: {gp_equity_pct:.1f}%")

    pref_rate = st.number_input("Preferred Return Rate (%)", value=8.0, step=0.1, key="pref_rate")
    gp_profit_share = st.number_input("GP Base Split after Pref (%)", value=20.0, step=1.0, key="gp_profit_share")
    include_catchup = st.checkbox("Include GP Catch-up?", value=False, key="include_catchup")

    st.markdown("**GP Promote / LP Cap**")
    promote_mode = st.selectbox("Promote Structure", options=[
        "IRR-Based Promote",
        "LP Return Cap",
        "None"
    ], index=0, key="promote_mode")

    if promote_mode == "IRR-Based Promote":
        promote_hurdle_irr = st.number_input("Promote Hurdle (Deal IRR %)", value=15.0, min_value=0.0, step=0.5, key="promote_hurdle_irr")
        gp_promote_share = st.number_input("GP Promote Split above Hurdle (%)", value=30.0, min_value=0.0, max_value=100.0, step=1.0, key="gp_promote_share")
        st.caption(f"Below {promote_hurdle_irr}% deal IRR → GP gets {gp_profit_share}% of residual. Above → GP gets {gp_promote_share}%.")
        lp_irr_cap = 999.0
    elif promote_mode == "LP Return Cap":
        lp_irr_cap = st.number_input("LP IRR Cap (%)", value=15.0, min_value=0.0, step=0.5, key="lp_irr_cap")
        st.caption(f"LP capped at {lp_irr_cap}% IRR. All exit proceeds above that go 100% to GP.")
        promote_hurdle_irr = 999.0
        gp_promote_share = gp_profit_share
    else:
        promote_hurdle_irr = 999.0
        gp_promote_share = gp_profit_share
        lp_irr_cap = 999.0

    enable_promote = (promote_mode == "IRR-Based Promote")

# Section 7: Exit Assumptions
with st.sidebar.expander("🚪 Exit Assumptions"):
    exit_cap_rate = st.number_input("Exit Cap Rate (%)", value=6.5, step=0.1, key="exit_cap_rate")
    broker_commission_pct = st.number_input("Broker Commission (%)", value=2.5, step=0.1, key="broker_commission_pct")
    exit_legal_pct = st.number_input("Exit Legal/Closing (%)", value=0.75, step=0.05, key="exit_legal_pct")
    disposition_fee_pct = st.number_input("Disposition Fee to GP (%)", value=1.0, step=0.1, key="disposition_fee_pct")

# EXPORT SECTION
st.sidebar.markdown("---")
st.sidebar.subheader("📥 Export to PDF")
deal_name = st.sidebar.text_input("Deal Name", "CVS Net Lease Investment", key="deal_name")
export_lp = st.sidebar.checkbox("LP Presentation", value=True)
export_gp = st.sidebar.checkbox("GP Analysis", value=False)
export_lender = st.sidebar.checkbox("Lender Presentation", value=False)

# PDF download buttons are rendered at the bottom of the script (after all tabs compute)

# MAIN AREA - Create tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "💵 Cash Flow Projections",
    "💧 Waterfall Distributions",
    "📊 Return Metrics",
    "🔍 Sensitivity Analysis",
    "📈 Debt Analysis"
])

with tab1:
    st.subheader("Annual Cash Flow Projections")

    # Lease runway (derived from sidebar inputs)
    runway = {
        'current_term_remaining': current_term_remaining_input,
        'options_remaining': num_renewal_options,
        'max_total_runway': current_term_remaining_input + (num_renewal_options * option_term_years)
    }

    # Display lease runway warnings and metrics
    if runway['current_term_remaining'] < 3:
        st.error(f"🚨 CRITICAL: Only {runway['current_term_remaining']} years remaining on current lease term!")
        st.warning("**Immediate Actions Required:**")
        st.write("• Negotiate renewal option exercise as condition of purchase")
        st.write("• Structure bridge loan only - permanent financing unavailable")
        st.write("• Plan exit before current term expires OR secure renewal commitment")
    elif runway['current_term_remaining'] < 7:
        st.warning(f"⚠️ Only {runway['current_term_remaining']} years remaining on current term")
        st.info("Permanent financing will require renewal option exercise")

    # Display lease runway metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Current Term Remaining", f"{runway['current_term_remaining']} years")
    with col2:
        st.metric("Options Remaining", f"{runway['options_remaining']}")
    with col3:
        st.metric("Maximum Total Runway", f"{runway['max_total_runway']} years")
    with col4:
        if renegotiate_lease:
            st.metric("Renegotiation", f"Year {renego_year}")
        else:
            st.metric("Renegotiation", "None")

    st.markdown("---")

    # Calculate NOI projection using multi-tenant model
    noi_df = calculate_multi_tenant_noi(st.session_state['tenants'], holding_period)

    # Initialize variables
    refi_results = None
    new_loan_amount = 0
    perm_payment = 0
    refi_proceeds = 0

    # Strategy-specific loan setup
    if deal_strategy == "Bridge-to-Permanent (Value-Add)":
        # Bridge loan at acquisition
        bridge_loan_amount = purchase_price * (bridge_ltv / 100)
        bridge_payment = calculate_bridge_loan_payment(
            bridge_loan_amount,
            bridge_rate,
            bridge_term,
            bridge_io
        )
        initial_loan_amount = bridge_loan_amount
        initial_debt_service = bridge_payment
    else:
        # Buy-and-Hold: Permanent loan at acquisition
        # Calculate initial permanent loan amount based on NOI
        year_1_noi = noi_df[noi_df['Year'] == 1]['NOI'].values[0]

        # Calculate max loan by LTV
        max_loan_by_ltv = purchase_price * (perm_ltv / 100)

        # Calculate max loan by DSCR
        max_debt_service = year_1_noi / target_dscr
        from calculations.financing import calculate_loan_from_payment
        max_loan_by_dscr = calculate_loan_from_payment(max_debt_service, perm_rate, perm_amort)

        # Use conservative or aggressive approach
        if use_conservative:
            initial_loan_amount = min(max_loan_by_ltv, max_loan_by_dscr)
        else:
            initial_loan_amount = max(max_loan_by_ltv, max_loan_by_dscr)

        initial_debt_service = calculate_perm_loan_payment(initial_loan_amount, perm_rate, perm_amort)
        bridge_loan_amount = 0
        bridge_payment = 0

    # Calculate LP and GP equity amounts based on percentages
    from calculations.cash_flows import calculate_total_project_cost

    if deal_strategy == "Bridge-to-Permanent (Value-Add)":
        costs_for_equity = calculate_total_project_cost(
            purchase_price, closing_costs_pct, bridge_orig_points,
            acquisition_fee_pct, bridge_loan_amount
        )
        total_equity_needed = costs_for_equity['total_uses'] - bridge_loan_amount + value_add_capex
    else:
        costs_for_equity = calculate_total_project_cost(
            purchase_price, closing_costs_pct, perm_orig_points_acq,
            acquisition_fee_pct, initial_loan_amount
        )
        total_equity_needed = costs_for_equity['total_uses'] - initial_loan_amount

    # Split equity by percentages
    lp_equity = total_equity_needed * (lp_equity_pct / 100)
    gp_equity = total_equity_needed * (gp_equity_pct / 100)

    # Create cash flow table
    cf_data = []
    for year in range(1, holding_period + 1):
        noi = noi_df[noi_df['Year'] == year]['NOI'].values[0]
        lease_status = noi_df[noi_df['Year'] == year]['Lease Status'].values[0]

        # Determine which loan is active based on strategy
        if deal_strategy == "Bridge-to-Permanent (Value-Add)":
            if year < refi_year:
                # Bridge loan period
                debt_service = bridge_payment
                loan_balance = calculate_bridge_loan_balance(
                    bridge_loan_amount, bridge_rate, bridge_term, year, bridge_io
                )
                loan_type = "Bridge"

            elif year == refi_year:
                # Refinance year
                # Check refi feasibility with lease
                refi_feasibility = check_refi_feasibility_with_lease(
                    runway['current_term_remaining'], runway['options_remaining'],
                    option_term_years, refi_year
                )

                # Calculate refi at beginning of year based on current NOI
                bridge_balance_at_refi = calculate_bridge_loan_balance(
                    bridge_loan_amount, bridge_rate, bridge_term, year - 1, bridge_io
                )

                refi_results = calculate_refinance(
                    noi, refi_valuation_method, refi_cap_rate,
                    fixed_refi_value, purchase_price, refi_year, appreciation_rate,
                    perm_rate, perm_ltv, perm_amort, target_dscr,
                    use_conservative, allow_cashout, max_cashout_pct,
                    bridge_balance_at_refi, bridge_prepay_penalty, perm_orig_points, refi_legal_costs
                )

                # Add feasibility status to refi_results
                refi_results['feasibility'] = refi_feasibility

                new_loan_amount = refi_results['new_loan_amount']
                perm_payment = calculate_perm_loan_payment(new_loan_amount, perm_rate, perm_amort)

                # Refi happens at beginning of year - pay perm loan for full year
                debt_service = perm_payment
                # Ending balance after 1 year of payments
                loan_balance = calculate_perm_loan_balance(
                    new_loan_amount, perm_rate, perm_amort, 1
                )
                refi_proceeds = refi_results['net_proceeds']
                loan_type = "Bridge→Perm"

            else:
                # Permanent loan period (years after refi)
                debt_service = perm_payment
                years_since_refi = year - refi_year
                # Balance calculation: year - refi_year gives years AFTER refi year,
                # but we need total years of payments (including refi year)
                loan_balance = calculate_perm_loan_balance(
                    new_loan_amount, perm_rate, perm_amort, years_since_refi + 1
                )
                loan_type = "Perm"

        else:
            # Buy-and-Hold strategy
            if year < refi_year or refi_year == 999:
                # Permanent loan from acquisition (no refi planned or not yet)
                debt_service = initial_debt_service
                loan_balance = calculate_perm_loan_balance(
                    initial_loan_amount, perm_rate, perm_amort, year
                )
                loan_type = "Perm"

            elif year == refi_year:
                # Cash-out refinance year
                refi_feasibility = check_refi_feasibility_with_lease(
                    runway['current_term_remaining'], runway['options_remaining'],
                    option_term_years, refi_year
                )

                # Current loan balance before refi
                current_balance = calculate_perm_loan_balance(
                    initial_loan_amount, perm_rate, perm_amort, year - 1
                )

                refi_results = calculate_refinance(
                    noi, refi_valuation_method, refi_cap_rate,
                    fixed_refi_value, purchase_price, refi_year, appreciation_rate,
                    perm_rate, perm_ltv, perm_amort, target_dscr,
                    use_conservative, allow_cashout, max_cashout_pct,
                    current_balance, 0, perm_orig_points, refi_legal_costs  # No prepay penalty on perm
                )

                refi_results['feasibility'] = refi_feasibility

                new_loan_amount = refi_results['new_loan_amount']
                perm_payment = calculate_perm_loan_payment(new_loan_amount, perm_rate, perm_amort)

                # Refi happens at beginning of year - pay new perm loan for full year
                debt_service = perm_payment
                loan_balance = calculate_perm_loan_balance(
                    new_loan_amount, perm_rate, perm_amort, 1
                )
                refi_proceeds = refi_results['net_proceeds']
                loan_type = "Perm Refi"

            else:
                # After refinance
                debt_service = perm_payment
                years_since_refi = year - refi_year
                loan_balance = calculate_perm_loan_balance(
                    new_loan_amount, perm_rate, perm_amort, years_since_refi + 1
                )
                loan_type = "Perm"

        # Operating expenses
        asset_mgmt_fee = lp_equity * (asset_mgmt_pct / 100)
        total_operating_expenses = capex_reserve + asset_mgmt_fee + admin_costs

        # Cash flow before debt
        cash_before_debt = noi - total_operating_expenses

        # Cash available for distribution (before refi proceeds)
        cash_before_refi = cash_before_debt - debt_service

        # Add refi proceeds in refi year
        if year == refi_year:
            cash_available = cash_before_refi + refi_proceeds
        else:
            cash_available = cash_before_refi

        # Value-add capex spend
        va_capex_this_year = value_add_capex if (year == value_add_year and value_add_capex > 0) else 0
        cash_available -= va_capex_this_year

        # DSCR
        dscr = calculate_dscr(noi, debt_service)

        cf_data.append({
            'Year': year,
            'Lease Status': lease_status,
            'NOI': noi,
            'Non-Operating Expenses': total_operating_expenses,
            'Value-Add CapEx': va_capex_this_year,
            'Cash Before Debt': cash_before_debt,
            'Debt Service': debt_service,
            'Cash Available': cash_available,
            'DSCR': dscr,
            'Loan Balance': loan_balance,
            'Loan Type': loan_type
        })

    cf_df = pd.DataFrame(cf_data)

    # Format and display
    st.dataframe(
        cf_df.style.format({
            'NOI': '${:,.0f}',
            'Non-Operating Expenses': '${:,.0f}',
            'Value-Add CapEx': '${:,.0f}',
            'Cash Before Debt': '${:,.0f}',
            'Debt Service': '${:,.0f}',
            'Cash Available': '${:,.0f}',
            'DSCR': '{:.2f}x',
            'Loan Balance': '${:,.0f}'
        }),
        use_container_width=True
    )

    # Display refinance details if refi occurred
    if refi_results:
        st.markdown("---")
        if deal_strategy == "Bridge-to-Permanent (Value-Add)":
            st.subheader(f"📊 Bridge-to-Permanent Refinance Analysis (Year {refi_year})")
        else:
            st.subheader(f"📊 Cash-Out Refinance Analysis (Year {refi_year})")

        # Display feasibility status
        feasibility = refi_results.get('feasibility', {})
        if feasibility:
            if not feasibility.get('feasible', True):
                st.error(f"{feasibility['status']}")
                st.warning(f"**{feasibility['requirement']}**")
            elif feasibility.get('requirement'):
                st.warning(f"{feasibility['status']}")
                st.info(f"**{feasibility['requirement']}**")
            else:
                st.success(f"{feasibility['status']}")

        # Property Valuation
        st.markdown("### Property Valuation at Refinance")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Property Value", f"${refi_results['property_value']:,.0f}")
            st.caption(refi_results['valuation_method'])
        with col2:
            st.metric("NOI at Refi", f"${refi_results['noi_at_refi']:,.0f}")
        with col3:
            implied_cap = (refi_results['noi_at_refi']/refi_results['property_value']*100)
            st.metric("Implied Cap Rate", f"{implied_cap:.2f}%")

        # Loan Sizing Analysis
        st.markdown("### Loan Sizing")
        sizing_data = [
            {
                'Constraint': 'LTV Constraint',
                'Calculation': f"{perm_ltv}% × ${refi_results['property_value']:,.0f}",
                'Max Loan': refi_results['max_loan_by_ltv'],
                'Binding': '✅' if refi_results['binding_constraint'] == 'LTV' else ''
            },
            {
                'Constraint': 'DSCR Constraint',
                'Calculation': f"${refi_results['noi_at_refi']:,.0f} / {target_dscr} DSCR",
                'Max Loan': refi_results['max_loan_by_dscr'],
                'Binding': '✅' if refi_results['binding_constraint'] == 'DSCR' else ''
            },
            {
                'Constraint': 'Selected Loan Amount',
                'Calculation': f"{'Lesser' if use_conservative else 'Greater'} of above",
                'Max Loan': refi_results['new_loan_amount'],
                'Binding': '📌'
            }
        ]
        sizing_df = pd.DataFrame(sizing_data)
        st.dataframe(
            sizing_df.style.format({'Max Loan': '${:,.0f}'}),
            use_container_width=True,
            hide_index=True
        )

        # Refinance Proceeds Waterfall
        st.markdown("### Refinance Proceeds")
        if deal_strategy == "Bridge-to-Permanent (Value-Add)":
            old_loan_label = "Bridge Loan Payoff"
        else:
            old_loan_label = "Old Perm Loan Payoff"

        proceeds_data = [
            ['New Loan Amount', refi_results['new_loan_amount']],
            [old_loan_label, -refi_results['bridge_payoff']],  # Reusing field name
            ['Prepayment Penalty', -refi_results['prepayment_penalty']],
            ['Perm Loan Origination', -refi_results['perm_origination']],
            ['Legal/Appraisal Costs', -refi_results['refi_legal_costs']],
            ['Net Proceeds', refi_results['net_proceeds']]
        ]
        proceeds_df = pd.DataFrame(proceeds_data, columns=['Item', 'Amount'])
        st.dataframe(
            proceeds_df.style.format({'Amount': '${:,.0f}'}),
            use_container_width=True,
            hide_index=True
        )

        # Cash-out analysis
        if refi_results.get('cashout_limited'):
            st.warning(f"⚠️ {refi_results['cashout_explanation']}")

        if refi_results['net_proceeds'] < 0:
            st.error(f"❌ Additional equity required: ${abs(refi_results['net_proceeds']):,.0f}")
            st.warning("**Refinance requires cash infusion - consider:**")
            st.write("• Wait for more NOI growth")
            st.write("• Negotiate better loan terms")
            st.write("• Extend bridge loan")
        elif refi_results['net_proceeds'] > 0:
            st.success(f"✅ Cash-out available: ${refi_results['net_proceeds']:,.0f}")
        else:
            st.info("Break-even refinance")

        # Final loan metrics
        st.markdown("### Post-Refinance Loan Metrics")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("New DSCR", f"{refi_results['final_dscr']:.2f}x")
        with col2:
            st.metric("New LTV", f"{refi_results['final_ltv']:.1f}%")
        with col3:
            st.metric("Equity Before", f"${refi_results['equity_before_refi']:,.0f}")
        with col4:
            st.metric("Equity After", f"${refi_results['equity_after_refi']:,.0f}")

    # Sources & Uses
    st.markdown("---")
    st.subheader("Sources & Uses of Funds")

    # Calculate sources & uses with equity amounts already determined
    if deal_strategy == "Bridge-to-Permanent (Value-Add)":
        sources_uses = calculate_sources(
            purchase_price, bridge_ltv, lp_equity, gp_equity,
            closing_costs_pct, bridge_orig_points, acquisition_fee_pct
        )
        loan_label = "Bridge Loan"
        loan_orig_label = "Bridge Origination"
    else:
        # Buy-and-hold uses permanent loan at acquisition
        perm_ltv_acquisition = (initial_loan_amount / purchase_price) * 100
        sources_uses = calculate_sources(
            purchase_price, perm_ltv_acquisition, lp_equity, gp_equity,
            closing_costs_pct, perm_orig_points_acq, acquisition_fee_pct
        )
        loan_label = "Permanent Loan"
        loan_orig_label = "Perm Origination"

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**SOURCES**")
        sources_data = pd.DataFrame([
            {'Source': loan_label, 'Amount': sources_uses['bridge_loan']},  # Reusing field name
            {'Source': f'LP Equity ({lp_equity_pct:.1f}%)', 'Amount': sources_uses['lp_equity']},
            {'Source': f'GP Equity ({gp_equity_pct:.1f}%)', 'Amount': sources_uses['gp_equity']},
            {'Source': 'TOTAL SOURCES', 'Amount': sources_uses['total_sources']}
        ])
        st.dataframe(
            sources_data.style.format({'Amount': '${:,.0f}'}),
            use_container_width=True,
            hide_index=True
        )

    with col2:
        st.markdown("**USES**")
        uses_rows = [
            {'Use': 'Purchase Price', 'Amount': sources_uses['uses']['purchase_price']},
            {'Use': 'Closing Costs', 'Amount': sources_uses['uses']['closing_costs']},
            {'Use': loan_orig_label, 'Amount': sources_uses['uses']['bridge_origination']},  # Reusing field name
            {'Use': 'Acquisition Fee', 'Amount': sources_uses['uses']['acquisition_fee']}
        ]
        # Add value-add capex if applicable
        if value_add_capex > 0:
            uses_rows.append({'Use': 'Value-Add CapEx', 'Amount': value_add_capex})

        # Add total
        total_uses_amount = sources_uses['uses']['total_uses'] + value_add_capex
        uses_rows.append({'Use': 'TOTAL USES', 'Amount': total_uses_amount})

        uses_data = pd.DataFrame(uses_rows)
        st.dataframe(
            uses_data.style.format({'Amount': '${:,.0f}'}),
            use_container_width=True,
            hide_index=True
        )

    # Key metrics
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Year 1 DSCR", f"{cf_df.iloc[0]['DSCR']:.2f}x")
    with col2:
        year_1_noi = cf_df.iloc[0]['NOI']
        st.metric("Going-In Cap Rate", f"{(year_1_noi/purchase_price*100):.2f}%")
    with col3:
        if deal_strategy == "Bridge-to-Permanent (Value-Add)":
            st.metric("Bridge LTV", f"{bridge_ltv:.1f}%")
        else:
            actual_ltv = (initial_loan_amount / purchase_price) * 100
            st.metric("Perm LTV", f"{actual_ltv:.1f}%")
    with col4:
        st.metric("Total Equity Required", f"${sources_uses['equity_needed']:,.0f}")

with tab2:
    st.subheader("💧 Waterfall Distribution Schedule")

    # Display waterfall structure
    st.markdown("### Distribution Waterfall Structure")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("LP Equity", f"${lp_equity:,.0f}", f"{lp_equity_pct:.1f}%")
    with col2:
        st.metric("GP Equity", f"${gp_equity:,.0f}", f"{gp_equity_pct:.1f}%")
    with col3:
        st.metric("Preferred Return", f"{pref_rate:.1f}%")

    # Show waterfall tiers
    st.markdown("#### Waterfall Tiers:")
    tiers_data = []

    tiers_data.append({
        'Tier': '1️⃣ Return OF Capital',
        'Description': 'Return equity contributions pro-rata by ownership %',
        'LP Share': f'{lp_equity_pct:.1f}%',
        'GP Share': f'{gp_equity_pct:.1f}%'
    })

    tiers_data.append({
        'Tier': '2️⃣ Preferred Return',
        'Description': f'{pref_rate}% annually on outstanding equity (including catch-up of unpaid pref)',
        'LP Share': f'{lp_equity_pct:.1f}%',
        'GP Share': f'{gp_equity_pct:.1f}%'
    })

    if include_catchup:
        tiers_data.append({
            'Tier': '3️⃣ GP Catch-Up',
            'Description': f'GP receives distributions until they have {gp_profit_share}% of all profits',
            'LP Share': '0%',
            'GP Share': '100%'
        })

    tier_num = 4 if include_catchup else 3
    tier_labels = {3: '3️⃣', 4: '4️⃣', 5: '5️⃣'}

    if promote_mode == "IRR-Based Promote":
        tiers_data.append({
            'Tier': f'{tier_labels[tier_num]} Residual Split (Base)',
            'Description': f'Annual cash flow split; exit residual below {promote_hurdle_irr}% deal IRR',
            'LP Share': f'{100 - gp_profit_share:.1f}%',
            'GP Share': f'{gp_profit_share:.1f}%'
        })
        tiers_data.append({
            'Tier': f'{tier_labels[tier_num + 1]} Promote Split',
            'Description': f'Exit residual above {promote_hurdle_irr}% deal IRR hurdle',
            'LP Share': f'{100 - gp_promote_share:.1f}%',
            'GP Share': f'{gp_promote_share:.1f}%'
        })
    elif promote_mode == "LP Return Cap":
        tiers_data.append({
            'Tier': f'{tier_labels[tier_num]} Residual Split (up to LP cap)',
            'Description': f'Exit residual until LP hits {lp_irr_cap}% IRR',
            'LP Share': f'{100 - gp_profit_share:.1f}%',
            'GP Share': f'{gp_profit_share:.1f}%'
        })
        tiers_data.append({
            'Tier': f'{tier_labels[tier_num + 1]} Above LP Cap',
            'Description': f'All exit proceeds above LP {lp_irr_cap}% IRR cap',
            'LP Share': '0%',
            'GP Share': '100%'
        })
    else:
        tiers_data.append({
            'Tier': f'{tier_labels[tier_num]} Residual Split',
            'Description': 'All remaining cash split by profit share',
            'LP Share': f'{100 - gp_profit_share:.1f}%',
            'GP Share': f'{gp_profit_share:.1f}%'
        })

    tiers_df = pd.DataFrame(tiers_data)
    st.dataframe(tiers_df, use_container_width=True, hide_index=True)

    # Calculate waterfall distributions
    st.markdown("---")
    st.markdown("### Annual Distributions")

    waterfall_df = calculate_multi_year_waterfall(
        cf_df, lp_equity, gp_equity, pref_rate,
        gp_profit_share, include_catchup
    )

    # Display waterfall table
    st.dataframe(
        waterfall_df.style.format({
            'Cash Available': '${:,.0f}',
            'LP Pref': '${:,.0f}',
            'LP Split': '${:,.0f}',
            'LP Total': '${:,.0f}',
            'LP Cumulative': '${:,.0f}',
            'GP Pref': '${:,.0f}',
            'GP Catch-up': '${:,.0f}',
            'GP Split': '${:,.0f}',
            'GP Total': '${:,.0f}',
            'GP Cumulative': '${:,.0f}',
            'LP Pref Deficit': '${:,.0f}',
            'GP Pref Deficit': '${:,.0f}'
        }),
        use_container_width=True
    )

    # Summary metrics
    st.markdown("---")
    st.markdown("### Distribution Summary")

    total_lp_distributions = waterfall_df['LP Total'].sum()
    total_gp_distributions = waterfall_df['GP Total'].sum()
    total_distributions = total_lp_distributions + total_gp_distributions

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total LP Distributions", f"${total_lp_distributions:,.0f}")
    with col2:
        st.metric("Total GP Distributions", f"${total_gp_distributions:,.0f}")
    with col3:
        lp_pct_of_total = (total_lp_distributions / total_distributions * 100) if total_distributions > 0 else 0
        st.metric("LP % of Total", f"{lp_pct_of_total:.1f}%")
    with col4:
        gp_pct_of_total = (total_gp_distributions / total_distributions * 100) if total_distributions > 0 else 0
        st.metric("GP % of Total", f"{gp_pct_of_total:.1f}%")

    # Check for unpaid pref at end
    final_lp_deficit = waterfall_df.iloc[-1]['LP Pref Deficit']
    final_gp_deficit = waterfall_df.iloc[-1]['GP Pref Deficit']

    if final_lp_deficit > 0 or final_gp_deficit > 0:
        st.warning(f"⚠️ **Unpaid Preferred Return at Exit:**")
        if final_lp_deficit > 0:
            st.write(f"• LP: ${final_lp_deficit:,.0f}")
        if final_gp_deficit > 0:
            st.write(f"• GP: ${final_gp_deficit:,.0f}")
        st.caption("These amounts should be addressed in exit proceeds waterfall")

with tab3:
    st.subheader("📊 Return Metrics")

    # --- Exit Sale Proceeds ---
    # Determine exit year NOI
    exit_year_noi = cf_df.iloc[-1]['NOI']
    exit_loan_balance = cf_df.iloc[-1]['Loan Balance']

    # Sale price from exit cap rate
    sale_price = exit_year_noi / (exit_cap_rate / 100)

    # Costs of sale
    broker_commission = sale_price * (broker_commission_pct / 100)
    exit_legal = sale_price * (exit_legal_pct / 100)
    disposition_fee = sale_price * (disposition_fee_pct / 100)
    total_sale_costs = broker_commission + exit_legal + disposition_fee

    # Net sale proceeds after paying off loan
    gross_equity_proceeds = sale_price - exit_loan_balance - total_sale_costs

    # --- Exit Waterfall (on gross equity proceeds) ---
    # Tier 1: Return of Capital (pro-rata LP/GP)
    total_equity_invested = lp_equity + gp_equity
    capital_returned = min(gross_equity_proceeds, total_equity_invested)
    lp_capital_return = capital_returned * (lp_equity / total_equity_invested) if total_equity_invested > 0 else 0
    gp_capital_return = capital_returned * (gp_equity / total_equity_invested) if total_equity_invested > 0 else 0
    remaining_after_capital = max(0, gross_equity_proceeds - total_equity_invested)

    # Tier 2: Unpaid preferred return catch-up from exit proceeds
    final_lp_deficit_exit = waterfall_df.iloc[-1]['LP Pref Deficit']
    final_gp_deficit_exit = waterfall_df.iloc[-1]['GP Pref Deficit']
    total_pref_deficit = final_lp_deficit_exit + final_gp_deficit_exit

    pref_catchup_paid = min(remaining_after_capital, total_pref_deficit)
    if total_pref_deficit > 0:
        lp_pref_catchup = pref_catchup_paid * (final_lp_deficit_exit / total_pref_deficit)
        gp_pref_catchup = pref_catchup_paid * (final_gp_deficit_exit / total_pref_deficit)
    else:
        lp_pref_catchup = 0
        gp_pref_catchup = 0
    remaining_after_pref = remaining_after_capital - pref_catchup_paid

    # Tier 3: GP Catch-up (if enabled)
    gp_exit_catchup = 0
    if include_catchup and remaining_after_pref > 0 and gp_profit_share > 0:
        total_annual_profits = waterfall_df['LP Split'].sum() + waterfall_df['GP Split'].sum() + waterfall_df['GP Catch-up'].sum()
        gp_annual_catchup_already = waterfall_df['GP Catch-up'].sum()
        gp_annual_split_already = waterfall_df['GP Split'].sum()

        total_residual_before_exit = total_annual_profits
        gp_share_of_annual = gp_annual_catchup_already + gp_annual_split_already
        target_gp_share = total_residual_before_exit * (gp_profit_share / 100)
        catchup_needed = max(0, target_gp_share - gp_share_of_annual)
        gp_exit_catchup = min(remaining_after_pref, catchup_needed)
        remaining_after_pref -= gp_exit_catchup

    # Tier 4: Residual split — IRR promote, LP cap, or plain split

    def _calc_irr_local(cashflows):
        """IRR via binary search — defined here so it's available before calc_irr below."""
        arr = np.array(cashflows, dtype=float)
        if np.sum(arr[1:]) <= 0:
            return None
        low, high = -0.5, 5.0
        for _ in range(200):
            mid = (low + high) / 2
            val = sum(cf / (1 + mid)**t for t, cf in enumerate(arr))
            if abs(val) < 0.01:
                return mid
            if val > 0:
                low = mid
            else:
                high = mid
        return mid

    # --- IRR-Based Promote ---
    actual_deal_irr = None
    promote_triggered = False
    lp_cap_hit = False
    lp_exit_split_base = 0   # portion split at base rate
    lp_exit_split_promote = 0  # portion split at promote rate (or capped)
    gp_exit_split_base = 0
    gp_exit_split_promote = 0

    if promote_mode == "IRR-Based Promote":
        # Deal IRR is total-level — doesn't depend on LP/GP split
        total_invested_deal = lp_equity + gp_equity
        deal_cfs_p = [-(total_invested_deal)]
        for i in range(len(waterfall_df)):
            annual_deal = waterfall_df.iloc[i]['LP Total'] + waterfall_df.iloc[i]['GP Total']
            if i == len(waterfall_df) - 1:
                annual_deal += gross_equity_proceeds
            deal_cfs_p.append(annual_deal)
        actual_deal_irr = _calc_irr_local(deal_cfs_p)

        if actual_deal_irr is not None and actual_deal_irr * 100 > promote_hurdle_irr:
            lp_exit_split = remaining_after_pref * ((100 - gp_promote_share) / 100)
            gp_exit_split = remaining_after_pref * (gp_promote_share / 100)
            promote_triggered = True
        else:
            lp_exit_split = remaining_after_pref * ((100 - gp_profit_share) / 100)
            gp_exit_split = remaining_after_pref * (gp_profit_share / 100)

    # --- LP Return Cap ---
    elif promote_mode == "LP Return Cap":
        # Binary-search for the LP exit cash that produces exactly lp_irr_cap.
        # LP total exit = lp_capital_return + lp_pref_catchup + lp_share_of_residual
        # We solve for lp_share_of_residual such that LP IRR = cap.

        # Build the fixed part of LP cash flows (annual distributions, no exit yet)
        lp_annual_cfs = []
        for i in range(len(waterfall_df)):
            lp_annual_cfs.append(waterfall_df.iloc[i]['LP Total'])

        def _lp_irr_given_exit_share(lp_residual_share):
            """LP IRR if LP gets lp_residual_share of the remaining_after_pref residual."""
            lp_exit_cash = lp_capital_return + lp_pref_catchup + lp_residual_share
            cfs = [-lp_equity]
            for i in range(len(lp_annual_cfs)):
                cf = lp_annual_cfs[i]
                if i == len(lp_annual_cfs) - 1:
                    cf += lp_exit_cash
                cfs.append(cf)
            return _calc_irr_local(cfs)

        # Check LP IRR if LP gets ALL the residual (upper bound)
        lp_irr_all = _lp_irr_given_exit_share(remaining_after_pref)
        # Check LP IRR if LP gets NONE of the residual (lower bound)
        lp_irr_none = _lp_irr_given_exit_share(0)

        target_cap = lp_irr_cap / 100.0

        if lp_irr_all is not None and lp_irr_all <= target_cap:
            # Even with all residual, LP doesn't hit cap — no cap triggered
            lp_exit_split = remaining_after_pref * ((100 - gp_profit_share) / 100)
            gp_exit_split = remaining_after_pref * (gp_profit_share / 100)
        elif lp_irr_none is not None and lp_irr_none >= target_cap:
            # LP already at or above cap with zero residual — all residual to GP
            lp_exit_split = 0
            gp_exit_split = remaining_after_pref
            lp_cap_hit = True
        else:
            # Binary search for the residual amount that puts LP exactly at cap
            low_r, high_r = 0.0, remaining_after_pref
            for _ in range(200):
                mid_r = (low_r + high_r) / 2
                irr_at_mid = _lp_irr_given_exit_share(mid_r)
                if irr_at_mid is None:
                    low_r = mid_r
                    continue
                if abs(irr_at_mid - target_cap) < 0.0001:
                    break
                if irr_at_mid < target_cap:
                    low_r = mid_r
                else:
                    high_r = mid_r
            # mid_r is the max LP residual before hitting cap
            # Below cap: split at base rate up to mid_r worth of LP share
            # The base-rate LP share that equals mid_r: lp_base_portion * (100-gp_profit_share)/100 = mid_r
            lp_base_portion = mid_r / ((100 - gp_profit_share) / 100) if gp_profit_share < 100 else 0
            gp_base_portion = lp_base_portion - mid_r  # GP's share of that same base-split chunk
            above_cap_residual = remaining_after_pref - lp_base_portion

            lp_exit_split = mid_r
            gp_exit_split = gp_base_portion + above_cap_residual  # GP gets base split on lower chunk + 100% of upper
            lp_cap_hit = True

    # --- No promote / cap ---
    else:
        lp_exit_split = remaining_after_pref * ((100 - gp_profit_share) / 100)
        gp_exit_split = remaining_after_pref * (gp_profit_share / 100)

    # Exit totals
    lp_exit_total = lp_capital_return + lp_pref_catchup + lp_exit_split
    gp_exit_total = gp_capital_return + gp_pref_catchup + gp_exit_catchup + gp_exit_split

    # --- Display Exit Analysis ---
    st.markdown("### Sale Analysis")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Exit Year NOI", f"${exit_year_noi:,.0f}")
    with col2:
        st.metric("Exit Cap Rate", f"{exit_cap_rate:.2f}%")
    with col3:
        st.metric("Sale Price", f"${sale_price:,.0f}")

    sale_proceeds_data = pd.DataFrame([
        ['Gross Sale Price', sale_price],
        ['Broker Commission', -broker_commission],
        ['Legal/Closing Costs', -exit_legal],
        ['Disposition Fee (GP)', -disposition_fee],
        ['Loan Payoff', -exit_loan_balance],
        ['Net Equity Proceeds', gross_equity_proceeds]
    ], columns=['Item', 'Amount'])

    st.dataframe(
        sale_proceeds_data.style.format({'Amount': '${:,.0f}'}),
        use_container_width=True,
        hide_index=True
    )

    # --- Exit Waterfall Display ---
    st.markdown("---")
    st.markdown("### Exit Proceeds Waterfall")

    exit_waterfall_rows = [
        ['Tier 1: Return of Capital', lp_capital_return, gp_capital_return, lp_capital_return + gp_capital_return],
        ['Tier 2: Unpaid Pref Catch-Up', lp_pref_catchup, gp_pref_catchup, lp_pref_catchup + gp_pref_catchup],
    ]
    if include_catchup:
        exit_waterfall_rows.append(['Tier 3: GP Catch-Up', 0, gp_exit_catchup, gp_exit_catchup])

    if promote_mode == "IRR-Based Promote":
        if promote_triggered:
            split_label = f'Residual Split (PROMOTE {gp_promote_share:.0f}% GP)'
        else:
            split_label = f'Residual Split (Base {gp_profit_share:.0f}% GP)'
    elif promote_mode == "LP Return Cap":
        if lp_cap_hit:
            split_label = f'Residual Split (LP CAPPED at {lp_irr_cap}%)'
        else:
            split_label = f'Residual Split (Base {gp_profit_share:.0f}% GP)'
    else:
        split_label = 'Residual Split'
    exit_waterfall_rows.append([split_label, lp_exit_split, gp_exit_split, lp_exit_split + gp_exit_split])
    exit_waterfall_rows.append(['TOTAL EXIT', lp_exit_total, gp_exit_total, lp_exit_total + gp_exit_total])

    exit_waterfall_data = pd.DataFrame(exit_waterfall_rows)

    exit_waterfall_data.columns = ['Tier', 'LP', 'GP', 'Total']
    st.dataframe(
        exit_waterfall_data.style.format({'LP': '${:,.0f}', 'GP': '${:,.0f}', 'Total': '${:,.0f}'}),
        use_container_width=True,
        hide_index=True
    )

    # Promote / cap status callout
    if promote_mode == "IRR-Based Promote":
        deal_irr_pct = actual_deal_irr * 100 if actual_deal_irr is not None else 0
        if promote_triggered:
            st.success(f"GP Promote triggered: Deal IRR {deal_irr_pct:.1f}% exceeds {promote_hurdle_irr}% hurdle — residual splits at {gp_promote_share:.0f}% GP / {100-gp_promote_share:.0f}% LP")
        else:
            st.info(f"GP Promote not triggered: Deal IRR {deal_irr_pct:.1f}% below {promote_hurdle_irr}% hurdle — residual splits at base {gp_profit_share:.0f}% GP / {100-gp_profit_share:.0f}% LP")
    elif promote_mode == "LP Return Cap":
        if lp_cap_hit:
            st.success(f"LP Return Cap triggered: LP capped at {lp_irr_cap}% IRR — excess exit proceeds go 100% to GP")
        else:
            st.info(f"LP Return Cap not triggered: LP IRR below {lp_irr_cap}% cap — base split applies")

    # --- Total Returns Summary (annual + exit combined) ---
    st.markdown("---")
    st.markdown("### Total Returns Summary")

    total_lp_annual = waterfall_df['LP Total'].sum()
    total_gp_annual = waterfall_df['GP Total'].sum()

    summary_rows = [
        ['Annual Distributions', total_lp_annual, total_gp_annual, total_lp_annual + total_gp_annual],
        ['Exit Proceeds', lp_exit_total, gp_exit_total, lp_exit_total + gp_exit_total],
        ['Total Cash Received', total_lp_annual + lp_exit_total, total_gp_annual + gp_exit_total,
         total_lp_annual + lp_exit_total + total_gp_annual + gp_exit_total],
        ['Equity Invested', lp_equity, gp_equity, lp_equity + gp_equity],
        ['Profit / (Loss)', total_lp_annual + lp_exit_total - lp_equity,
         total_gp_annual + gp_exit_total - gp_equity,
         (total_lp_annual + lp_exit_total - lp_equity) + (total_gp_annual + gp_exit_total - gp_equity)],
    ]
    summary_df = pd.DataFrame(summary_rows, columns=['', 'LP', 'GP', 'Total'])
    st.dataframe(
        summary_df.style.format({'LP': '${:,.0f}', 'GP': '${:,.0f}', 'Total': '${:,.0f}'}),
        use_container_width=True,
        hide_index=True
    )

    # --- IRR and Equity Multiple Calculation ---
    st.markdown("---")
    st.markdown("### Investor Return Metrics")

    # Build cash flow streams for LP and GP
    # Year 0: initial investment (negative)
    # Years 1-N: annual distributions
    # Year N: add exit proceeds to final year distribution

    lp_cashflows = [-lp_equity]
    gp_cashflows = [-gp_equity]

    for i in range(len(waterfall_df)):
        lp_annual = waterfall_df.iloc[i]['LP Total']
        gp_annual = waterfall_df.iloc[i]['GP Total']

        # Add exit proceeds in final year
        if i == len(waterfall_df) - 1:
            lp_annual += lp_exit_total
            gp_annual += gp_exit_total

        lp_cashflows.append(lp_annual)
        gp_cashflows.append(gp_annual)

    # IRR calculation using numpy
    def calc_irr(cashflows):
        """Calculate IRR using numpy polynomial root finding"""
        if len(cashflows) < 2:
            return None
        # numpy.irr is deprecated, use numpy_financial or manual calc
        # Manual Newton's method approach
        cashflows_arr = np.array(cashflows, dtype=float)

        # Quick check: if all cashflows after 0 are <= 0, no positive IRR
        if np.sum(cashflows_arr[1:]) <= 0:
            return None

        # Try a range of rates
        def npv(rate):
            return sum(cf / (1 + rate)**t for t, cf in enumerate(cashflows_arr))

        # Binary search / Newton between -50% and 500%
        low, high = -0.5, 5.0
        for _ in range(200):
            mid = (low + high) / 2
            val = npv(mid)
            if abs(val) < 0.01:
                return mid
            if val > 0:
                low = mid
            else:
                high = mid
        return mid

    lp_irr = calc_irr(lp_cashflows)
    gp_irr = calc_irr(gp_cashflows)

    # Equity multiples
    lp_total_return = sum(lp_cashflows[1:])  # all inflows
    gp_total_return = sum(gp_cashflows[1:])
    lp_em = lp_total_return / lp_equity if lp_equity > 0 else 0
    gp_em = gp_total_return / gp_equity if gp_equity > 0 else 0

    # Cash-on-cash returns by year
    lp_coc_list = []
    gp_coc_list = []
    for i in range(len(waterfall_df)):
        lp_coc = (waterfall_df.iloc[i]['LP Total'] / lp_equity * 100) if lp_equity > 0 else 0
        gp_coc = (waterfall_df.iloc[i]['GP Total'] / gp_equity * 100) if gp_equity > 0 else 0
        lp_coc_list.append(lp_coc)
        gp_coc_list.append(gp_coc)

    # Display key metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**LP Returns**")
        st.metric("IRR", f"{lp_irr*100:.2f}%" if lp_irr is not None else "N/A")
        st.metric("Equity Multiple", f"{lp_em:.2f}x")
        st.metric("Total Return", f"${lp_total_return:,.0f}")
    with col2:
        st.markdown("**GP Returns**")
        st.metric("IRR", f"{gp_irr*100:.2f}%" if gp_irr is not None else "N/A")
        st.metric("Equity Multiple", f"{gp_em:.2f}x")
        st.metric("Total Return", f"${gp_total_return:,.0f}")
    with col3:
        st.markdown("**Deal Level**")
        total_invested = lp_equity + gp_equity
        total_returned = lp_total_return + gp_total_return
        deal_em = total_returned / total_invested if total_invested > 0 else 0
        deal_cashflows = [-total_invested] + [lp_cashflows[i] + gp_cashflows[i] for i in range(1, len(lp_cashflows))]
        deal_irr = calc_irr(deal_cashflows)
        st.metric("Deal IRR", f"{deal_irr*100:.2f}%" if deal_irr is not None else "N/A")
        st.metric("Deal Equity Multiple", f"{deal_em:.2f}x")
        st.metric("Total Equity Invested", f"${total_invested:,.0f}")

    # Cash-on-Cash table (includes exit row)
    st.markdown("---")
    st.markdown("### Annual Cash-on-Cash Returns")

    coc_years = list(waterfall_df['Year'].values) + ['Exit']
    coc_lp_dist = list(waterfall_df['LP Total'].values) + [lp_exit_total]
    coc_gp_dist = list(waterfall_df['GP Total'].values) + [gp_exit_total]
    coc_lp_pct = lp_coc_list + [(lp_exit_total / lp_equity * 100) if lp_equity > 0 else 0]
    coc_gp_pct = gp_coc_list + [(gp_exit_total / gp_equity * 100) if gp_equity > 0 else 0]

    coc_data = pd.DataFrame({
        'Year': coc_years,
        'LP Distribution': coc_lp_dist,
        'LP CoC (%)': coc_lp_pct,
        'GP Distribution': coc_gp_dist,
        'GP CoC (%)': coc_gp_pct
    })
    st.dataframe(
        coc_data.style.format({
            'LP Distribution': '${:,.0f}',
            'LP CoC (%)': '{:.2f}%',
            'GP Distribution': '${:,.0f}',
            'GP CoC (%)': '{:.2f}%'
        }),
        use_container_width=True,
        hide_index=True
    )

with tab4:
    st.subheader("🔍 Sensitivity Analysis")

    # Helper: recalculate deal IRR given a purchase price and exit cap rate
    def quick_deal_irr(pp, exit_cap, base_rent_val, bump_freq, bump_pct_val, ann_esc,
                       hold_period, current_term_rem, lease_runway_val, yrs_elapsed,
                       strategy, bridge_ltv_val, bridge_rate_val, bridge_term_val, bridge_io_val,
                       perm_rate_val, perm_amort_val, perm_ltv_val, target_dscr_val,
                       use_cons, lp_eq_pct, gp_eq_pct, pref_rate_val, gp_ps,
                       incl_catchup, closing_pct, orig_points, acq_fee_pct,
                       capex_res, asset_mgmt_p, admin_c,
                       refi_yr, refi_val_method, refi_cap, fixed_refi_val, apprec_rate,
                       allow_co, max_co_pct, bridge_prepay_pen, perm_orig_pts, refi_legal,
                       broker_comm_pct, exit_legal_p, disp_fee_pct, rent_struct):
        """Stripped-down IRR calc for sensitivity - returns (deal_irr, lp_irr)"""
        try:
            if renegotiate_lease and renego_year <= hold_period:
                noi_pre = calculate_noi_projection_with_lease(
                    base_rent_val, rent_struct, bump_freq, bump_pct_val, ann_esc,
                    renego_year - 1, current_term_rem, lease_runway_val, yrs_elapsed
                )
                noi_post = calculate_noi_projection_with_lease(
                    renego_rent, renego_structure, renego_bump_freq,
                    renego_bump_pct, renego_escalator, hold_period - (renego_year - 1),
                    renego_new_term, renego_new_term, 0
                )
                noi_post['Year'] = noi_post['Year'] + (renego_year - 1)
                noi_df_s = pd.concat([noi_pre, noi_post], ignore_index=True)
            else:
                noi_df_s = calculate_noi_projection_with_lease(
                    base_rent_val, rent_struct, bump_freq, bump_pct_val, ann_esc,
                    hold_period, current_term_rem, lease_runway_val, yrs_elapsed
                )

            # Loan setup
            if strategy == "Bridge-to-Permanent (Value-Add)":
                bl_amount = pp * (bridge_ltv_val / 100)
                bl_payment = calculate_bridge_loan_payment(bl_amount, bridge_rate_val, bridge_term_val, bridge_io_val)
                init_loan = bl_amount
                init_ds = bl_payment
            else:
                y1_noi = noi_df_s[noi_df_s['Year'] == 1]['NOI'].values[0]
                max_ltv_l = pp * (perm_ltv_val / 100)
                max_ds = y1_noi / target_dscr_val
                from calculations.financing import calculate_loan_from_payment as clf
                max_dscr_l = clf(max_ds, perm_rate_val, perm_amort_val)
                init_loan = min(max_ltv_l, max_dscr_l) if use_cons else max(max_ltv_l, max_dscr_l)
                init_ds = calculate_perm_loan_payment(init_loan, perm_rate_val, perm_amort_val)
                bl_amount = 0
                bl_payment = 0

            # Equity
            from calculations.cash_flows import calculate_total_project_cost as ctpc
            if strategy == "Bridge-to-Permanent (Value-Add)":
                costs_s = ctpc(pp, closing_pct, orig_points, acq_fee_pct, bl_amount)
                eq_needed = costs_s['total_uses'] - bl_amount + value_add_capex
            else:
                costs_s = ctpc(pp, closing_pct, orig_points, acq_fee_pct, init_loan)
                eq_needed = costs_s['total_uses'] - init_loan

            lp_eq = eq_needed * (lp_eq_pct / 100)
            gp_eq = eq_needed * (gp_eq_pct / 100)

            # Cash flows
            cf_list = []
            new_ln = 0
            pm = 0
            rp = 0
            refi_res = None

            for year in range(1, hold_period + 1):
                noi_v = noi_df_s[noi_df_s['Year'] == year]['NOI'].values[0]

                if strategy == "Bridge-to-Permanent (Value-Add)":
                    if year < refi_yr:
                        ds = bl_payment
                        lb = calculate_bridge_loan_balance(bl_amount, bridge_rate_val, bridge_term_val, year, bridge_io_val)
                    elif year == refi_yr:
                        bb = calculate_bridge_loan_balance(bl_amount, bridge_rate_val, bridge_term_val, year-1, bridge_io_val)
                        refi_res = calculate_refinance(
                            noi_v, refi_val_method, refi_cap, fixed_refi_val, pp, refi_yr, apprec_rate,
                            perm_rate_val, perm_ltv_val, perm_amort_val, target_dscr_val,
                            use_cons, allow_co, max_co_pct, bb, bridge_prepay_pen, perm_orig_pts, refi_legal
                        )
                        new_ln = refi_res['new_loan_amount']
                        pm = calculate_perm_loan_payment(new_ln, perm_rate_val, perm_amort_val)
                        ds = pm
                        lb = calculate_perm_loan_balance(new_ln, perm_rate_val, perm_amort_val, 1)
                        rp = refi_res['net_proceeds']
                    else:
                        ds = pm
                        lb = calculate_perm_loan_balance(new_ln, perm_rate_val, perm_amort_val, year - refi_yr + 1)
                else:
                    if year < refi_yr or refi_yr == 999:
                        ds = init_ds
                        lb = calculate_perm_loan_balance(init_loan, perm_rate_val, perm_amort_val, year)
                    elif year == refi_yr:
                        cb = calculate_perm_loan_balance(init_loan, perm_rate_val, perm_amort_val, year-1)
                        refi_res = calculate_refinance(
                            noi_v, refi_val_method, refi_cap, fixed_refi_val, pp, refi_yr, apprec_rate,
                            perm_rate_val, perm_ltv_val, perm_amort_val, target_dscr_val,
                            use_cons, allow_co, max_co_pct, cb, 0, perm_orig_pts, refi_legal
                        )
                        new_ln = refi_res['new_loan_amount']
                        pm = calculate_perm_loan_payment(new_ln, perm_rate_val, perm_amort_val)
                        ds = pm
                        lb = calculate_perm_loan_balance(new_ln, perm_rate_val, perm_amort_val, 1)
                        rp = refi_res['net_proceeds']
                    else:
                        ds = pm
                        lb = calculate_perm_loan_balance(new_ln, perm_rate_val, perm_amort_val, year - refi_yr + 1)

                amf = lp_eq * (asset_mgmt_p / 100)
                opex = capex_res + amf + admin_c
                cbd = noi_v - opex
                cbr = cbd - ds
                ca = cbr + (rp if year == refi_yr else 0)
                ca -= value_add_capex if (year == value_add_year and value_add_capex > 0) else 0

                cf_list.append({'Year': year, 'NOI': noi_v, 'Cash Available': ca, 'Loan Balance': lb})

            cf_df_s = pd.DataFrame(cf_list)

            # Waterfall
            wf_df = calculate_multi_year_waterfall(cf_df_s, lp_eq, gp_eq, pref_rate_val, gp_ps, incl_catchup)

            # Exit
            exit_noi_s = cf_df_s.iloc[-1]['NOI']
            exit_bal_s = cf_df_s.iloc[-1]['Loan Balance']
            sp = exit_noi_s / (exit_cap / 100)
            bc = sp * (broker_comm_pct / 100)
            el = sp * (exit_legal_p / 100)
            df_fee = sp * (disp_fee_pct / 100)
            gep = sp - exit_bal_s - bc - el - df_fee

            # Exit waterfall simplified
            total_eq_inv = lp_eq + gp_eq
            cap_ret = min(gep, total_eq_inv)
            rem = max(0, gep - total_eq_inv)

            # Pref deficit catchup
            fl_def = wf_df.iloc[-1]['LP Pref Deficit']
            fg_def = wf_df.iloc[-1]['GP Pref Deficit']
            tot_def = fl_def + fg_def
            pc_paid = min(rem, tot_def)
            if tot_def > 0:
                lpc = pc_paid * (fl_def / tot_def)
                gpc = pc_paid * (fg_def / tot_def)
            else:
                lpc, gpc = 0, 0
            rem -= pc_paid

            # GP catchup (exit)
            gce = 0
            if incl_catchup and rem > 0 and gp_ps > 0:
                tot_res = wf_df['LP Split'].sum() + wf_df['GP Split'].sum() + wf_df['GP Catch-up'].sum()
                gp_so_far = wf_df['GP Catch-up'].sum() + wf_df['GP Split'].sum()
                tgt = tot_res * (gp_ps / 100)
                cu_need = max(0, tgt - gp_so_far)
                gce = min(rem, cu_need)
                rem -= gce

            # IRR helper (must be defined before promote/cap block uses it)
            def _irr(cfs):
                arr = np.array(cfs, dtype=float)
                if np.sum(arr[1:]) <= 0:
                    return None
                low, high = -0.5, 5.0
                for _ in range(200):
                    mid = (low + high) / 2
                    val = sum(c / (1 + mid)**t for t, c in enumerate(arr))
                    if abs(val) < 0.01:
                        return mid
                    if val > 0:
                        low = mid
                    else:
                        high = mid
                return mid

            # Promote / LP cap logic
            if promote_mode == "IRR-Based Promote":
                total_eq_chk = lp_eq + gp_eq
                deal_cfs_chk = [-(total_eq_chk)]
                for i in range(len(wf_df)):
                    annual_chk = wf_df.iloc[i]['LP Total'] + wf_df.iloc[i]['GP Total']
                    if i == len(wf_df) - 1:
                        annual_chk += gep
                    deal_cfs_chk.append(annual_chk)
                d_irr_chk = _irr(deal_cfs_chk)

                if d_irr_chk is not None and d_irr_chk * 100 > promote_hurdle_irr:
                    lp_es = rem * ((100 - gp_promote_share) / 100)
                    gp_es = rem * (gp_promote_share / 100)
                else:
                    lp_es = rem * ((100 - gp_ps) / 100)
                    gp_es = rem * (gp_ps / 100)

            elif promote_mode == "LP Return Cap":
                # Binary search for LP residual share that hits the cap
                lp_cap_ret_s = (cap_ret * lp_eq / total_eq_inv) if total_eq_inv > 0 else 0
                lp_fixed_exit = lp_cap_ret_s + lpc  # capital return + pref catchup

                def _lp_irr_at_share(lp_res_share):
                    cfs = [-lp_eq]
                    for i in range(len(wf_df)):
                        cf = wf_df.iloc[i]['LP Total']
                        if i == len(wf_df) - 1:
                            cf += lp_fixed_exit + lp_res_share
                        cfs.append(cf)
                    return _irr(cfs)

                lp_irr_max = _lp_irr_at_share(rem)
                target_cap_s = lp_irr_cap / 100.0

                if lp_irr_max is None or lp_irr_max <= target_cap_s:
                    # Cap not hit — base split
                    lp_es = rem * ((100 - gp_ps) / 100)
                    gp_es = rem * (gp_ps / 100)
                else:
                    lp_irr_zero = _lp_irr_at_share(0)
                    if lp_irr_zero is not None and lp_irr_zero >= target_cap_s:
                        lp_es = 0
                        gp_es = rem
                    else:
                        lo, hi = 0.0, rem
                        for _ in range(200):
                            mid_s = (lo + hi) / 2
                            irr_m = _lp_irr_at_share(mid_s)
                            if irr_m is None:
                                lo = mid_s
                                continue
                            if abs(irr_m - target_cap_s) < 0.0001:
                                break
                            if irr_m < target_cap_s:
                                lo = mid_s
                            else:
                                hi = mid_s
                        # mid_s = max LP residual before cap; rest goes to GP
                        base_chunk = mid_s / ((100 - gp_ps) / 100) if gp_ps < 100 else 0
                        lp_es = mid_s
                        gp_es = (base_chunk - mid_s) + (rem - base_chunk)
            else:
                lp_es = rem * ((100 - gp_ps) / 100)
                gp_es = rem * (gp_ps / 100)

            lp_exit = (cap_ret * lp_eq / total_eq_inv if total_eq_inv > 0 else 0) + lpc + lp_es
            gp_exit = (cap_ret * gp_eq / total_eq_inv if total_eq_inv > 0 else 0) + gpc + gce + gp_es

            # IRR
            lp_cfs = [-lp_eq]
            gp_cfs = [-gp_eq]
            for i in range(len(wf_df)):
                la = wf_df.iloc[i]['LP Total'] + (lp_exit if i == len(wf_df)-1 else 0)
                ga = wf_df.iloc[i]['GP Total'] + (gp_exit if i == len(wf_df)-1 else 0)
                lp_cfs.append(la)
                gp_cfs.append(ga)

            deal_cfs = [-(lp_eq + gp_eq)] + [lp_cfs[i] + gp_cfs[i] for i in range(1, len(lp_cfs))]

            return _irr(deal_cfs), _irr(lp_cfs)
        except Exception:
            return None, None

    # Shared call helper to reduce repetition
    _orig_pts = bridge_orig_points if deal_strategy == "Bridge-to-Permanent (Value-Add)" else perm_orig_points_acq
    _perm_pts = perm_orig_points if deal_strategy == "Bridge-to-Permanent (Value-Add)" else 0
    _refi_leg = refi_legal_costs if deal_strategy == "Bridge-to-Permanent (Value-Add)" or (deal_strategy == "Buy-and-Hold with Permanent Financing" and exit_strategy == "Cash-Out Refinance") else 0

    def _run(pp_v, exit_cap_v, perm_rate_v, refi_cap_v):
        return quick_deal_irr(
            pp_v, exit_cap_v, base_annual_rent, bump_frequency, bump_percentage, annual_escalator,
            holding_period, runway['current_term_remaining'], runway['max_total_runway'], years_elapsed,
            deal_strategy, bridge_ltv, bridge_rate, bridge_term, bridge_io,
            perm_rate_v, perm_amort, perm_ltv, target_dscr,
            use_conservative, lp_equity_pct, gp_equity_pct, pref_rate, gp_profit_share,
            include_catchup, closing_costs_pct, _orig_pts, acquisition_fee_pct,
            capex_reserve, asset_mgmt_pct, admin_costs,
            refi_year, refi_valuation_method, refi_cap_v, fixed_refi_value, appreciation_rate,
            allow_cashout, max_cashout_pct, bridge_prepay_penalty, _perm_pts, _refi_leg,
            broker_commission_pct, exit_legal_pct, disposition_fee_pct, rent_structure_type
        )

    exit_cap_range = [5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0]

    # --- Sensitivity Table 1: Exit Cap Rate vs Perm Interest Rate (Deal IRR %) ---
    st.markdown("### Exit Cap Rate vs Perm Interest Rate (Deal IRR %)")
    perm_rate_range = [round(perm_rate + d, 1) for d in [-1.0, -0.5, 0.0, 0.5, 1.0]]

    sens1_data = {}
    for pr in perm_rate_range:
        row_vals = []
        for ec in exit_cap_range:
            d_irr, _ = _run(purchase_price, ec, pr, refi_cap_rate)
            row_vals.append(f"{d_irr*100:.1f}%" if d_irr is not None else "N/A")
        sens1_data[f"Perm Rate {pr}%"] = row_vals

    sens1_df = pd.DataFrame(sens1_data, index=[f"{ec}%" for ec in exit_cap_range])
    sens1_df.index.name = "Exit Cap Rate"
    st.dataframe(sens1_df, use_container_width=True)

    # --- Sensitivity Table 2: Exit Cap Rate vs Perm Interest Rate (LP IRR %) ---
    st.markdown("---")
    st.markdown("### Exit Cap Rate vs Perm Interest Rate (LP IRR %)")
    perm_rate_range = [round(perm_rate + d, 1) for d in [-1.0, -0.5, 0.0, 0.5, 1.0]]

    sens2_data = {}
    for pr in perm_rate_range:
        row_vals = []
        for ec in exit_cap_range:
            _, lp_irr_v = _run(purchase_price, ec, pr, refi_cap_rate)
            row_vals.append(f"{lp_irr_v*100:.1f}%" if lp_irr_v is not None else "N/A")
        sens2_data[f"Perm Rate {pr}%"] = row_vals

    sens2_df = pd.DataFrame(sens2_data, index=[f"{ec}%" for ec in exit_cap_range])
    sens2_df.index.name = "Exit Cap Rate"
    st.dataframe(sens2_df, use_container_width=True)

with tab5:
    st.subheader("📈 Debt Analysis")

    # Build debt metrics table from cf_df
    from calculations.financing import calculate_debt_yield, calculate_ltv

    debt_data = []
    for _, row in cf_df.iterrows():
        noi_val = row['NOI']
        ds_val = row['Debt Service']
        bal_val = row['Loan Balance']

        dscr_val = calculate_dscr(noi_val, ds_val)
        dy_val = calculate_debt_yield(noi_val, bal_val)
        ltv_val = calculate_ltv(bal_val, sale_price)  # Use exit sale price as rough value proxy

        debt_data.append({
            'Year': int(row['Year']),
            'Loan Type': row['Loan Type'],
            'Loan Balance': bal_val,
            'NOI': noi_val,
            'Debt Service': ds_val,
            'DSCR': dscr_val,
            'Debt Yield (%)': dy_val,
            'LTV (%)': ltv_val
        })

    debt_df = pd.DataFrame(debt_data)

    # Summary metrics at top
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_dscr = debt_df['DSCR'].min()
        min_dscr_year = int(debt_df.loc[debt_df['DSCR'].idxmin(), 'Year'])
        st.metric("Min DSCR", f"{min_dscr:.2f}x", f"Year {min_dscr_year}")
    with col2:
        max_ltv = debt_df['LTV (%)'].max()
        max_ltv_year = int(debt_df.loc[debt_df['LTV (%)'].idxmax(), 'Year'])
        st.metric("Max LTV", f"{max_ltv:.1f}%", f"Year {max_ltv_year}")
    with col3:
        min_dy = debt_df['Debt Yield (%)'].min()
        st.metric("Min Debt Yield", f"{min_dy:.2f}%")
    with col4:
        total_ds = debt_df['Debt Service'].sum()
        st.metric("Total Debt Service", f"${total_ds:,.0f}")

    # Lender comfort check
    st.markdown("### Lender Comfort Check")
    issues = []
    if min_dscr < 1.0:
        issues.append(f"DSCR below 1.0x in Year {min_dscr_year} ({min_dscr:.2f}x) -- negative cash flow")
    elif min_dscr < 1.25:
        issues.append(f"DSCR below 1.25x in Year {min_dscr_year} ({min_dscr:.2f}x) -- tight coverage")
    if max_ltv > 80:
        issues.append(f"LTV exceeds 80% in Year {max_ltv_year} ({max_ltv:.1f}%)")

    if issues:
        for issue in issues:
            st.warning(f"Warning: {issue}")
    else:
        st.success("All debt metrics within typical lender thresholds")

    # Full table
    st.markdown("---")
    st.markdown("### Debt Metrics by Year")
    st.dataframe(
        debt_df.style.format({
            'Loan Balance': '${:,.0f}',
            'NOI': '${:,.0f}',
            'Debt Service': '${:,.0f}',
            'DSCR': '{:.2f}x',
            'Debt Yield (%)': '{:.2f}%',
            'LTV (%)': '{:.1f}%'
        }),
        use_container_width=True,
        hide_index=True
    )

    # Principal paydown table (for amortizing loans)
    st.markdown("---")
    st.markdown("### Principal Paydown Schedule")
    paydown_data = []
    for i in range(len(debt_df)):
        row = debt_df.iloc[i]
        year_num = int(row['Year'])

        # Determine starting balance
        if i == 0:
            if deal_strategy == "Bridge-to-Permanent (Value-Add)":
                starting_balance = bridge_loan_amount
            else:
                starting_balance = initial_loan_amount
        else:
            starting_balance = debt_df.iloc[i-1]['Loan Balance']

        ending_balance = row['Loan Balance']

        # Check if this is a refi year (loan balance increases)
        is_refi_year = (ending_balance > starting_balance) if i > 0 else False

        if is_refi_year:
            # In refi year: calculate based on old loan, then reset for new loan
            # The debt service shown is for the NEW loan (which started this year)
            # Interest = new loan rate × new loan balance (for 1 year)
            if deal_strategy == "Bridge-to-Permanent (Value-Add)" and year_num == refi_year:
                # Bridge to perm: new perm loan started this year
                interest_paid = ending_balance * (perm_rate / 100)
            else:
                # Buy-and-hold refi
                interest_paid = ending_balance * (perm_rate / 100)

            principal_paid = row['Debt Service'] - interest_paid
            # Reset starting balance to new loan amount for display
            starting_balance = ending_balance
        else:
            # Normal year: principal = starting - ending
            principal_paid = starting_balance - ending_balance
            interest_paid = row['Debt Service'] - principal_paid

        paydown_data.append({
            'Year': year_num,
            'Starting Balance': starting_balance,
            'Principal Paid': max(0, principal_paid),
            'Interest Paid': interest_paid,
            'Ending Balance': ending_balance
        })

    paydown_df = pd.DataFrame(paydown_data)
    st.dataframe(
        paydown_df.style.format({
            'Starting Balance': '${:,.0f}',
            'Principal Paid': '${:,.0f}',
            'Interest Paid': '${:,.0f}',
            'Ending Balance': '${:,.0f}'
        }),
        use_container_width=True,
        hide_index=True
    )

# =========================================================================
# PDF EXPORT  –  runs after all tabs so every variable is populated
# =========================================================================
from pdf_export import build_lp_report, build_gp_report, build_lender_report

_report_data = {
    # property
    'deal_name':            deal_name,
    'property_name':        property_name,
    'property_address':     property_address,
    'property_city_state':  property_city_state,
    'tenant_name':          tenant_name,
    'property_type':        property_type,
    # deal
    'purchase_price':       purchase_price,
    'holding_period':       holding_period,
    'deal_strategy':        deal_strategy,
    # equity / loan
    'lp_equity':            lp_equity,
    'gp_equity':            gp_equity,
    'initial_loan_amount':  initial_loan_amount,
    # loan params (lender report)
    'bridge_rate':          bridge_rate,
    'bridge_ltv':           bridge_ltv,
    'bridge_term':          bridge_term,
    'bridge_io':            bridge_io,
    'perm_rate':            perm_rate,
    'perm_ltv':             perm_ltv,
    'perm_amort':           perm_amort,
    'target_dscr':          target_dscr,
    # waterfall params
    'pref_rate':            pref_rate,
    'promote_mode':         promote_mode,
    'promote_hurdle_irr':   promote_hurdle_irr,
    'gp_promote_share':     gp_promote_share,
    'lp_irr_cap':           lp_irr_cap if lp_irr_cap != 999.0 else None,
    # exit
    'exit_cap_rate':        exit_cap_rate,
    'sale_price':           sale_price,
    'exit_loan_balance':    cf_df.iloc[-1]['Loan Balance'],
    # DataFrames
    'cf_df':                cf_df,
    'waterfall_df':         waterfall_df,
    # computed returns  (IRRs stored as %, e.g. 21.3)
    'lp_annual_total':      total_lp_annual,
    'gp_annual_total':      total_gp_annual,
    'lp_exit_total':        lp_exit_total,
    'gp_exit_total':        gp_exit_total,
    'deal_irr':             deal_irr * 100 if deal_irr is not None else None,
    'lp_irr':               lp_irr  * 100 if lp_irr  is not None else None,
    'gp_irr':               gp_irr  * 100 if gp_irr  is not None else None,
}

_safe_name = deal_name.replace(" ", "_").replace("/", "-") or "deal"

if export_lp:
    st.sidebar.download_button(
        "⬇️ LP Presentation",
        build_lp_report(_report_data),
        file_name=f"{_safe_name}_LP.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
if export_gp:
    st.sidebar.download_button(
        "⬇️ GP Analysis",
        build_gp_report(_report_data),
        file_name=f"{_safe_name}_GP.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
if export_lender:
    st.sidebar.download_button(
        "⬇️ Lender Presentation",
        build_lender_report(_report_data),
        file_name=f"{_safe_name}_Lender.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

# Footer
st.markdown("---")
st.markdown("*Built with Streamlit for Commercial Real Estate Underwriting*")
