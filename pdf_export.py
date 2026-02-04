"""
PDF export for CRE Underwriting Model.
Three reports: LP Investment Summary, GP Deal Analysis, Lender Presentation.
Each builder takes a `data` dict and returns PDF bytes.
"""
from fpdf import FPDF
from datetime import date

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
NAVY    = (27, 42, 74)
NAVY_LT = (41, 65, 122)
DK_GRAY = (60, 60, 60)
LT_GRAY = (245, 245, 245)
WHITE   = (255, 255, 255)
BLUE_BG = (232, 240, 254)

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def _d(v):
    """Currency, no decimals, with negative sign."""
    if v is None:
        return "N/A"
    s = f"${abs(v):,.0f}"
    return f"-{s}" if v < 0 else s

def _p(v):
    """Percentage (input already in percent, e.g. 8.0 -> '8.0%')."""
    return f"{v:.1f}%" if v is not None else "N/A"

def _x(v):
    """Ratio / multiple (e.g. 1.25 -> '1.25x')."""
    return f"{v:.2f}x" if v is not None else "N/A"


# ---------------------------------------------------------------------------
# Base PDF class
# ---------------------------------------------------------------------------
class CREReport(FPDF):
    def __init__(self, subtitle=""):
        super().__init__()
        self.subtitle  = subtitle
        self._deal     = ""

    # -- page callbacks -----------------------------------------------------
    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 20, 'F')
        self.set_text_color(*WHITE)
        self.set_font('Helvetica', 'B', 12)
        self.set_xy(12, 4)
        self.cell(0, 7, self._deal)
        self.set_font('Helvetica', '', 9)
        self.set_xy(12, 12)
        self.cell(0, 5, self.subtitle)
        self.set_text_color(*DK_GRAY)
        self.set_y(25)

    def footer(self):
        self.set_y(-14)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(150)
        self.cell(0, 5, f"Generated {date.today().isoformat()}   |   Page {self.page_no()}", align='C')

    # -- helpers ------------------------------------------------------------
    def section(self, title):
        """Navy section-header bar."""
        self.set_y(self.get_y() + 2)
        self.set_fill_color(*NAVY_LT)
        self.set_text_color(*WHITE)
        self.set_font('Helvetica', 'B', 9)
        self.cell(0, 7, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*DK_GRAY)
        self.set_y(self.get_y() + 2)

    def kv(self, label, value, highlight=False):
        """Key / value row."""
        y = self.get_y()
        if highlight:
            self.set_fill_color(*BLUE_BG)
            self.rect(10, y, self.epw, 5.5, 'F')
        self.set_font('Helvetica', '', 9)
        self.set_x(12)
        self.cell(70, 5.5, label)
        self.set_font('Helvetica', 'B', 9)
        self.cell(0, 5.5, str(value), new_x="LMARGIN", new_y="NEXT")

    def table(self, headers, rows, widths=None, font_size=8, highlight_rows=None):
        """
        Render a bordered, shaded table with navy header.
        widths   – column widths in mm (default: evenly split).
        highlight_rows – set of row indices to shade blue.
        Automatically repeats header on page break.
        """
        if widths is None:
            w = self.epw / len(headers)
            widths = [w] * len(headers)
        if highlight_rows is None:
            highlight_rows = set()

        row_h = max(font_size * 0.42, 5)  # min 5 mm

        def _header_row():
            self.set_fill_color(*NAVY)
            self.set_text_color(*WHITE)
            self.set_font('Helvetica', 'B', font_size)
            for i, h in enumerate(headers):
                self.cell(widths[i], row_h, h, border=1, fill=True,
                          align='L' if i == 0 else 'R')
            self.ln(row_h)
            self.set_text_color(*DK_GRAY)

        _header_row()

        for ri, row in enumerate(rows):
            # page-break guard – repeat header on new page
            if self.get_y() + row_h > self.h - 20:
                self.add_page()
                _header_row()

            # row fill
            if ri in highlight_rows:
                self.set_fill_color(*BLUE_BG)
            elif ri % 2 == 0:
                self.set_fill_color(*LT_GRAY)
            else:
                self.set_fill_color(*WHITE)

            for ci, val in enumerate(row):
                bold = (ci == 0) or (ri in highlight_rows)
                self.set_font('Helvetica', 'B' if bold else '', font_size)
                self.cell(widths[ci], row_h, str(val), border=1, fill=True,
                          align='L' if ci == 0 else 'R')
            self.ln(row_h)

        self.ln(3)


# =========================================================================
# LP  –  Investment Summary
# =========================================================================
def build_lp_report(d: dict) -> bytes:
    pdf = CREReport(subtitle="LP Investment Summary")
    pdf._deal = d.get('deal_name', 'Deal')
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # ---- deal overview ----
    pdf.section("DEAL OVERVIEW")
    pdf.kv("Property",      d.get('property_name') or d.get('property_address') or 'N/A')
    pdf.kv("Location",      d.get('property_city_state', ''))
    pdf.kv("Tenant",        d.get('tenant_name', 'N/A'))
    pdf.kv("Purchase Price",_d(d['purchase_price']))
    pdf.kv("Hold Period",   f"{d['holding_period']} years")
    pdf.kv("Strategy",      d['deal_strategy'])

    # ---- your investment ----
    pdf.section("YOUR INVESTMENT")
    pdf.kv("Equity Invested",  _d(d['lp_equity']), highlight=True)
    pdf.kv("Preferred Return", _p(d['pref_rate']))
    pdf.kv("Promote / Cap",    d['promote_mode'])
    if d['promote_mode'] == 'IRR-Based Promote':
        pdf.kv("Hurdle IRR",            _p(d.get('promote_hurdle_irr')))
        pdf.kv("GP Share Above Hurdle", _p(d.get('gp_promote_share')))
    elif d['promote_mode'] == 'LP Return Cap':
        pdf.kv("LP IRR Cap", _p(d.get('lp_irr_cap')))

    # ---- annual distributions ----
    pdf.section("ANNUAL CASH DISTRIBUTIONS")
    rows = []
    for _, r in d['waterfall_df'].iterrows():
        coc = r['LP Total'] / d['lp_equity'] * 100 if d['lp_equity'] else 0
        rows.append([str(int(r['Year'])), _d(r['LP Total']), _p(coc)])
    pdf.table(['Year', 'Distribution', 'Cash-on-Cash'],
              rows, widths=[30, 85, 75])

    # ---- total returns ----
    ann  = d.get('lp_annual_total', 0)
    ext  = d.get('lp_exit_total', 0)
    tot  = ann + ext
    prof = tot - d['lp_equity']
    pdf.section("TOTAL RETURNS")
    pdf.table(
        ['', 'Amount'],
        [
            ['Annual Distributions', _d(ann)],
            ['Exit Proceeds',        _d(ext)],
            ['Total Cash Received',  _d(tot)],
            ['Equity Invested',      _d(d['lp_equity'])],
            ['Profit / (Loss)',      _d(prof)],
        ],
        widths=[110, 80],
        highlight_rows={2, 4}
    )

    # ---- key metrics ----
    pdf.section("KEY METRICS")
    em   = tot / d['lp_equity'] if d['lp_equity'] else 0
    avg  = ann / d['lp_equity'] / d['holding_period'] * 100 if d['lp_equity'] and d['holding_period'] else 0
    pdf.kv("LP IRR",          _p(d.get('lp_irr')),  highlight=True)
    pdf.kv("Equity Multiple", _x(em),               highlight=True)
    pdf.kv("Avg Annual CoC",  _p(avg))

    return bytes(pdf.output())


# =========================================================================
# GP  –  Full Deal Analysis
# =========================================================================
def build_gp_report(d: dict) -> bytes:
    pdf = CREReport(subtitle="GP Deal Analysis")
    pdf._deal = d.get('deal_name', 'Deal')
    pdf.set_auto_page_break(auto=True, margin=18)

    # ---------- page 1: overview + cash flows ----------
    pdf.add_page()

    pdf.section("DEAL OVERVIEW")
    pdf.kv("Property",      d.get('property_name') or d.get('property_address') or 'N/A')
    pdf.kv("Location",      d.get('property_city_state', ''))
    pdf.kv("Tenant",        d.get('tenant_name', 'N/A'))
    pdf.kv("Purchase Price",_d(d['purchase_price']))
    pdf.kv("Hold Period",   f"{d['holding_period']} years")
    pdf.kv("Strategy",      d['deal_strategy'])

    pdf.section("SOURCES & USES")
    loan = d['initial_loan_amount']
    lp   = d['lp_equity']
    gp   = d['gp_equity']
    pdf.table(
        ['', 'Amount'],
        [
            ['Loan',          _d(loan)],
            ['LP Equity',     _d(lp)],
            ['GP Equity',     _d(gp)],
            ['Total Sources', _d(loan + lp + gp)],
        ],
        widths=[110, 80],
        highlight_rows={3}
    )

    pdf.section("CASH FLOW PROJECTIONS")
    rows = []
    for _, r in d['cf_df'].iterrows():
        rows.append([
            str(int(r['Year'])),
            _d(r['NOI']),
            _d(r['Debt Service']),
            _d(r['Cash Available']),
            f"{r['DSCR']:.2f}x",
        ])
    pdf.table(['Year', 'NOI', 'Debt Service', 'Cash Avail', 'DSCR'],
              rows, widths=[22, 42, 42, 42, 42])

    # ---------- page 2: waterfall + exit ----------
    pdf.add_page()

    pdf.section("WATERFALL DISTRIBUTIONS")
    rows = []
    for _, r in d['waterfall_df'].iterrows():
        rows.append([
            str(int(r['Year'])),
            _d(r['LP Pref']),  _d(r['GP Pref']),
            _d(r['LP Split']), _d(r['GP Split']),
            _d(r['LP Total']), _d(r['GP Total']),
        ])
    pdf.table(
        ['Year', 'LP Pref', 'GP Pref', 'LP Split', 'GP Split', 'LP Total', 'GP Total'],
        rows,
        widths=[22, 28, 28, 28, 28, 28, 28],
        font_size=7
    )

    # exit & total returns
    lp_ann = d.get('lp_annual_total', 0)
    gp_ann = d.get('gp_annual_total', 0)
    lp_ext = d.get('lp_exit_total', 0)
    gp_ext = d.get('gp_exit_total', 0)
    lp_tot = lp_ann + lp_ext
    gp_tot = gp_ann + gp_ext

    pdf.section("EXIT & TOTAL RETURNS")
    pdf.table(
        ['', 'LP', 'GP', 'Total'],
        [
            ['Annual Distributions', _d(lp_ann),  _d(gp_ann),  _d(lp_ann + gp_ann)],
            ['Exit Proceeds',        _d(lp_ext),  _d(gp_ext),  _d(lp_ext + gp_ext)],
            ['Total Cash Received',  _d(lp_tot),  _d(gp_tot),  _d(lp_tot + gp_tot)],
            ['Equity Invested',      _d(lp),      _d(gp),      _d(lp + gp)],
            ['Profit / (Loss)',      _d(lp_tot - lp), _d(gp_tot - gp), _d(lp_tot + gp_tot - lp - gp)],
        ],
        widths=[50, 45, 45, 50],
        highlight_rows={2, 4}
    )

    # return metrics
    pdf.section("RETURN METRICS")
    lp_em = lp_tot / lp if lp else 0
    gp_em = gp_tot / gp if gp else 0
    pdf.kv("Deal IRR",          _p(d.get('deal_irr')),  highlight=True)
    pdf.kv("LP IRR",            _p(d.get('lp_irr')),    highlight=True)
    pdf.kv("GP IRR",            _p(d.get('gp_irr')),    highlight=True)
    pdf.kv("LP Equity Multiple",_x(lp_em))
    pdf.kv("GP Equity Multiple",_x(gp_em))

    # promote / cap status line
    if d['promote_mode'] == 'IRR-Based Promote':
        irr_v  = d.get('deal_irr') or 0
        hurdle = d.get('promote_hurdle_irr', 0)
        tag    = "TRIGGERED" if irr_v > hurdle else "Not triggered"
        pdf.kv("Promote Status", f"{tag}  (Deal IRR {_p(irr_v)} vs {_p(hurdle)} hurdle)")
    elif d['promote_mode'] == 'LP Return Cap':
        irr_v = d.get('lp_irr') or 0
        cap   = d.get('lp_irr_cap', 0)
        tag   = "CAPPED" if irr_v >= cap - 0.05 else "Not capped"
        pdf.kv("LP Cap Status", f"{tag}  (LP IRR {_p(irr_v)} vs {_p(cap)} cap)")

    return bytes(pdf.output())


# =========================================================================
# Lender  –  Debt & Coverage
# =========================================================================
def build_lender_report(d: dict) -> bytes:
    pdf = CREReport(subtitle="Lender Presentation")
    pdf._deal = d.get('deal_name', 'Deal')
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # ---- property ----
    pdf.section("PROPERTY SUMMARY")
    pdf.kv("Property",      d.get('property_name') or d.get('property_address') or 'N/A')
    pdf.kv("Location",      d.get('property_city_state', ''))
    pdf.kv("Tenant",        d.get('tenant_name', 'N/A'))
    pdf.kv("Property Type", d.get('property_type', 'N/A'))
    pdf.kv("Purchase Price",_d(d['purchase_price']))

    # ---- loan terms ----
    pdf.section("LOAN TERMS")
    if d['deal_strategy'] == 'Bridge-to-Permanent (Value-Add)':
        pdf.kv("Loan Type",     "Bridge Loan")
        pdf.kv("Loan Amount",   _d(d['initial_loan_amount']))
        pdf.kv("Interest Rate", _p(d.get('bridge_rate', 0)))
        pdf.kv("LTV at Close",  _p(d.get('bridge_ltv', 0)))
        pdf.kv("Term",          f"{d.get('bridge_term', 0)} years")
        pdf.kv("Structure",     "Interest Only" if d.get('bridge_io') else "Amortizing")
    else:
        pdf.kv("Loan Type",      "Permanent Loan")
        pdf.kv("Loan Amount",    _d(d['initial_loan_amount']))
        pdf.kv("Interest Rate",  _p(d.get('perm_rate', 0)))
        pdf.kv("LTV at Close",   _p(d.get('perm_ltv', 0)))
        pdf.kv("Amortization",   f"{d.get('perm_amort', 0)} years")
        pdf.kv("Target DSCR",    _x(d.get('target_dscr', 0)))

    # ---- debt coverage table ----
    pdf.section("DEBT COVERAGE ANALYSIS")
    rows = []
    min_dscr = 999
    for _, r in d['cf_df'].iterrows():
        dy   = r['NOI'] / r['Loan Balance'] * 100 if r['Loan Balance'] > 0 else 0
        dscr = r['DSCR']
        if dscr < min_dscr:
            min_dscr = dscr
        rows.append([
            str(int(r['Year'])),
            _d(r['NOI']),
            _d(r['Debt Service']),
            f"{dscr:.2f}x",
            _d(r['Loan Balance']),
            _p(dy),
        ])
    pdf.table(
        ['Year', 'NOI', 'Debt Service', 'DSCR', 'Loan Balance', 'Debt Yield'],
        rows,
        widths=[22, 35, 35, 28, 38, 32]
    )

    # min DSCR callout
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(0, 5, f"Minimum DSCR across hold: {min_dscr:.2f}x", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ---- exit / payoff ----
    pdf.section("EXIT / PAYOFF SUMMARY")
    sale = d.get('sale_price', 0)
    bal  = d.get('exit_loan_balance', 0)
    ltv  = bal / sale * 100 if sale > 0 else 0
    pdf.kv("Exit Year",     str(d['holding_period']))
    pdf.kv("Exit Cap Rate", _p(d.get('exit_cap_rate', 0)))
    pdf.kv("Sale Price",    _d(sale))
    pdf.kv("Loan Payoff",   _d(bal))
    pdf.kv("LTV at Exit",   _p(ltv))
    pdf.kv("Equity at Exit",_d(sale - bal), highlight=True)

    return bytes(pdf.output())
