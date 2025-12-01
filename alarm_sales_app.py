import streamlit as st
from datetime import datetime
import json
import os
import pandas as pd

# ----- PRISER / KONSTANTER -----

BASE_OVER_70 = 30990        # Paketpris 70+
BASE_UNDER_70 = 32400       # Paketpris under 70

EXTRA_MAGNET = 1000
EXTRA_CAMERA = 2200
EXTRA_FIRE = 2000

START_FEE = 594             # engångsavgift
ADMIN_MONTHLY = 49          # per månad
INSTALLATION_COST = 5000    # bakas in i månadsbetalningen

# När larmet är avbetalat: service/uppkoppling
SERVICE_HALF_YEAR = 594
SERVICE_MONTHLY = SERVICE_HALF_YEAR / 6  # ≈ 99 kr/mån

PAYMENT_OPTIONS = [
    ("90 dagar (3 mån)", 3),
    ("12 månader", 12),
    ("24 månader", 24),
    ("36 månader", 36),
    ("60 månader", 60),
    ("72 månader", 72),
    ("120 månader", 120),
]

CUSTOMER_FILE = "customers.json"

# Provision/bonus-konstanter
BASE_COMMISSION_PER_DEAL = 2500          # Startpaket provision
INSTALL_COMMISSION_RATE = 0.20           # 20% av installationskostnaden
UPSELL_COMMISSION_RATE = 0.10            # 10% på merförsäljning
COMPENSATION_PENALTY_RATE = 0.20         # -20% på total provision vid kundkompensation
MILE_COMP = 25.50                        # kr/mil


# ----- HJÄLPFUNKTIONER -----


def compute_plans(financed_amount: float):
    """Räknar ut alla planer (månad, total) för alla bindningstider."""
    plans = []
    for label, months in PAYMENT_OPTIONS:
        monthly_fin = financed_amount / months
        monthly_total = monthly_fin + ADMIN_MONTHLY
        total_cost = monthly_total * months + START_FEE
        plans.append(
            {
                "label": label,
                "months": months,
                "monthly": monthly_total,
                "total": total_cost,
            }
        )
    return plans


def choose_best_plan_for_budget(plans, target_monthly: float):
    """
    Bästa plan för given max-månadskostnad:
    - Om det finns alternativ <= budget: ta det som är närmast budget (högst monthly).
    - Annars: ta lägsta månadskostnaden.
    """
    under_or_equal = [p for p in plans if p["monthly"] <= target_monthly]
    if under_or_equal:
        best = max(under_or_equal, key=lambda p: p["monthly"])
        status = "within"
    else:
        best = min(plans, key=lambda p: p["monthly"])
        status = "above"
    return best, status


def choose_discount_plan_to_match_price(plans, target_monthly: float, tolerance: float):
    """
    Matcha rabatterad plan mot kundens önskade månadskostnad:
    1. Ta planer inom [target - tol, target + tol]
    2. Bland dem: kortast bindningstid
    3. Annars: plan närmast target
    """
    lower = target_monthly - tolerance
    upper = target_monthly + tolerance
    candidates = [p for p in plans if lower <= p["monthly"] <= upper]

    if candidates:
        candidates.sort(key=lambda p: (p["months"], abs(p["monthly"] - target_monthly)))
        return candidates[0], True

    nearest = min(plans, key=lambda p: abs(p["monthly"] - target_monthly))
    return nearest, False


def seller_breakdown(
    base_price,
    is_over_70,
    magnet_count,
    camera_count,
    fire_count,
    charged_magnet,
    charged_camera,
    charged_fire,
    financed_amount,
    plan,
    tag,
):
    """Returnerar detaljer endast för säljaren."""
    extras_total_full = (
        magnet_count * EXTRA_MAGNET
        + camera_count * EXTRA_CAMERA
        + fire_count * EXTRA_FIRE
    )

    extras_charged = (
        (magnet_count * EXTRA_MAGNET if charged_magnet else 0)
        + (camera_count * EXTRA_CAMERA if charged_camera else 0)
        + (fire_count * EXTRA_FIRE if charged_fire else 0)
    )

    lines = []
    lines.append(f"### [{tag}] Detaljer för säljare")
    lines.append(f"- Kundkategori: {'70+' if is_over_70 else 'Under 70'}")
    lines.append(f"- Grundpris: {base_price:.0f} kr")
    lines.append(f"- Tillval (alla): {extras_total_full:.0f} kr")
    lines.append(f"- Tillval debiterade: {extras_charged:.0f} kr")
    if magnet_count > 0:
        lines.append(
            f"  - Extra magneter: {magnet_count} st á {EXTRA_MAGNET} kr "
            f"({'debiteras' if charged_magnet else 'BJUDS'})"
        )
    if camera_count > 0:
        lines.append(
            f"  - Kameror: {camera_count} st á {EXTRA_CAMERA} kr "
            f"({'debiteras' if charged_camera else 'BJUDS'})"
        )
    if fire_count > 0:
        lines.append(
            f"  - Brandvarnare: {fire_count} st á {EXTRA_FIRE} kr "
            f"({'debiteras' if charged_fire else 'BJUDS'})"
        )

    lines.append(f"- Installation: {INSTALLATION_COST:.0f} kr")
    lines.append(f"- Finansierat belopp (exkl start): {financed_amount:.0f} kr")
    lines.append(f"- Vald plan: {plan['label']} ({plan['months']} mån)")
    lines.append(f"- Månadskostnad: {plan['monthly']:.2f} kr")
    lines.append(f"- Totalkostnad inkl startavgift: {plan['total']:.2f} kr")

    return "\n".join(lines)


def load_customers():
    if os.path.exists(CUSTOMER_FILE):
        try:
            with open(CUSTOMER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_customers(customers):
    try:
        with open(CUSTOMER_FILE, "w", encoding="utf-8") as f:
            json.dump(customers, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def generate_offer_text(
    customer_name,
    customer_phone,
    customer_address,
    note,
    standard_plan,
    discount_plan,
    base_price,
    is_over_70,
    magnet_count,
    camera_count,
    fire_count,
    extras_total_full,
    extras_charged,
    discount_amount_total,
    discount_percent_total,
    discount_percent_extras,
):
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    plan_used = discount_plan or standard_plan
    label_used = "Rabatterat erbjudande" if discount_plan else "Standarderbjudande"

    lines = []
    lines.append("STL Kalkylator - Offert")
    lines.append(f"Datum: {today}")
    lines.append("")
    lines.append(f"Kund: {customer_name or '-'}")
    lines.append(f"Telefon: {customer_phone or '-'}")
    lines.append(f"Adress: {customer_address or '-'}")
    lines.append("")
    if note:
        lines.append(f"Anteckning: {note}")
        lines.append("")
    lines.append(f"Kundkategori: {'70+' if is_over_70 else 'Under 70'}")
    lines.append(f"Grundpris paket: {base_price:.0f} kr")
    lines.append(f"Tillval (totalt värde): {extras_total_full:.0f} kr")
    lines.append(f"Tillval debiterade: {extras_charged:.0f} kr")
    lines.append(f"Installation: {INSTALLATION_COST:.0f} kr")
    if magnet_count or camera_count or fire_count:
        lines.append(f"- Magneter: {magnet_count} st")
        lines.append(f"- Kameror: {camera_count} st")
        lines.append(f"- Brandvarnare: {fire_count} st")
    lines.append("")
    lines.append(f"{label_used}:")
    lines.append(
        f"- Plan: {plan_used['label']} ({plan_used['months']} månader)"
    )
    lines.append(
        f"- Månadskostnad (inkl admin): {plan_used['monthly']:.2f} kr/mån"
    )
    lines.append(
        f"- Totalkostnad inkl startavgift: {plan_used['total']:.2f} kr"
    )
    lines.append("")
    if discount_plan and discount_amount_total > 0:
        lines.append("Rabatt (jämfört med standard):")
        lines.append(f"- Sparat belopp totalt: {discount_amount_total:.0f} kr")
        lines.append(f"- Rabatt totalt: {discount_percent_total:.1f} %")
        if extras_total_full > 0:
            lines.append(
                f"- Rabatt på tillvalsvärde: {discount_percent_extras:.1f} %"
            )
    return "\n".join(lines)


def bonus_for_net_sales(net_sales: int) -> int:
    """Returnerar månadsbonus baserat på antal nettoförsäljningar."""
    if net_sales >= 50:
        return 50000
    if net_sales >= 40:
        return 40000
    if net_sales >= 30:
        return 30000
    if net_sales >= 20:
        return 15000
    if net_sales >= 15:
        return 10000
    if net_sales >= 10:
        return 5000
    return 0


# ----- STREAMLIT UI -----


st.set_page_config(page_title="STL Kalkylator", layout="wide")

st.title("📊 STL Kalkylator")

# Session för kundlista
if "customers" not in st.session_state:
    st.session_state.customers = load_customers()

# ---- SIDOMENY ----

st.sidebar.header("Kunduppgifter")

customer_name = st.sidebar.text_input("Kundnamn")
customer_phone = st.sidebar.text_input("Telefon")
customer_address = st.sidebar.text_input("Adress")
customer_note = st.sidebar.text_area("Anteckning", height=80)

st.sidebar.header("Kund & paket")

age_choice = st.sidebar.radio("Kundens ålder", ["70 år eller äldre", "Under 70"])
is_over_70 = age_choice == "70 år eller äldre"
base_price = BASE_OVER_70 if is_over_70 else BASE_UNDER_70

st.sidebar.subheader("Tillval – antal")
magnet_count = st.sidebar.number_input(
    "Antal extra magneter", min_value=0, step=1, value=0
)
camera_count = st.sidebar.number_input(
    "Antal kameror", min_value=0, step=1, value=0
)
fire_count = st.sidebar.number_input(
    "Antal brandvarnare", min_value=0, step=1, value=0
)

st.sidebar.subheader("Rabatt / bjussa")
charged_magnet = magnet_count > 0 and not st.sidebar.checkbox(
    "Bjud på ALLA magneter"
)
charged_camera = camera_count > 0 and not st.sidebar.checkbox(
    "Bjud på ALLA kameror"
)
charged_fire = fire_count > 0 and not st.sidebar.checkbox(
    "Bjud på ALLA brandvarnare"
)

st.sidebar.header("Prisinställningar")

term_labels = [label for label, _ in PAYMENT_OPTIONS]
selected_term_label = st.sidebar.selectbox("Önskad bindningstid", term_labels)

desired_monthly = st.sidebar.number_input(
    "Kundens önskade belopp (kr/mån)",
    min_value=0.0,
    value=800.0,
    step=50.0,
)

tolerance = st.sidebar.slider(
    "Tillåten skillnad vid rabatt (± kr/mån)",
    min_value=0,
    max_value=500,
    value=50,
    step=10,
)

st.sidebar.header("Provision / bonus")
net_sales_month = st.sidebar.number_input(
    "Nettoförsäljningar denna månad (inkl denna affär)",
    min_value=0,
    step=1,
    value=0,
)
miles_driven = st.sidebar.number_input(
    "Körda mil för denna affär (ungefär)",
    min_value=0.0,
    step=1.0,
    value=0.0,
)

st.sidebar.header("Visning")
mobile_mode = st.sidebar.checkbox("Mobil-läge (1 kolumn)", value=False)

# ---- BERÄKNINGAR FÖR STANDARDERBJUDANDE ----

extras_total_full = (
    magnet_count * EXTRA_MAGNET
    + camera_count * EXTRA_CAMERA
    + fire_count * EXTRA_FIRE
)

financed_full = base_price + extras_total_full + INSTALLATION_COST
plans_full = compute_plans(financed_full)

# vald plan efter önskad bindningstid
selected_plan_full = next(
    p for p in plans_full if p["label"] == selected_term_label
)

best_budget_plan, budget_status = choose_best_plan_for_budget(
    plans_full, desired_monthly
)

cols_standard = st.columns(1 if mobile_mode else 2)

st.subheader("1️⃣ Standarderbjudande (utan rabatt)")

with cols_standard[0]:
    st.markdown(f"**Vald bindningstid:** {selected_plan_full['label']}")
    st.write(
        f"💰 Månadskostnad: **{selected_plan_full['monthly']:.2f} kr/mån**"
    )
    st.write(
        f"⏱ Bindningstid: **{selected_plan_full['months']} månader**"
    )
    st.write(
        f"📦 Totalkostnad inkl startavgift: **{selected_plan_full['total']:.2f} kr**"
    )

    diff_vs_desired = selected_plan_full["monthly"] - desired_monthly
    if desired_monthly > 0:
        if abs(diff_vs_desired) < 1:
            st.info("Ligger i princip exakt på kundens önskade belopp.")
        elif diff_vs_desired > 0:
            st.warning(
                f"Ca {diff_vs_desired:.0f} kr/mån över kundens önskade belopp "
                f"({desired_monthly:.0f} kr/mån)."
            )
        else:
            st.success(
                f"Ca {-diff_vs_desired:.0f} kr/mån UNDER kundens önskade belopp "
                f"({desired_monthly:.0f} kr/mån)."
            )

    st.markdown("**Talking point till kund:**")
    st.write(
        f"\"Med den här lösningen landar du på ungefär **{selected_plan_full['monthly']:.0f} kr per månad** "
        f"i **{selected_plan_full['months']} månader**, inklusive installation och adminavgift. "
        f"Totalt blir det ungefär **{selected_plan_full['total']:.0f} kr**, inklusive startavgiften på {START_FEE} kr.\""
    )

    st.markdown("---")
    st.markdown("**Bästa plan utifrån kundens önskade belopp:**")
    st.write(
        f"{best_budget_plan['label']} – ca {best_budget_plan['monthly']:.0f} kr/mån "
        f"(totalt ~{best_budget_plan['total']:.0f} kr)."
    )
    if budget_status == "within":
        st.info("Planen ligger inom kundens budget.")
    else:
        st.warning(
            "Inga planer ligger under kundens budget – visar lägsta möjliga månadskostnad."
        )

with cols_standard[-1]:
    st.markdown("**Alla planer (utan rabatt)**")
    st.dataframe(
        {
            "Plan": [p["label"] for p in plans_full],
            "Månader": [p["months"] for p in plans_full],
            "kr/mån": [round(p["monthly"], 2) for p in plans_full],
            "Totalt (kr)": [round(p["total"], 2) for p in plans_full],
        },
        use_container_width=True,
    )

with st.expander("Säljar-detaljer – Standard"):
    st.markdown(
        seller_breakdown(
            base_price,
            is_over_70,
            magnet_count,
            camera_count,
            fire_count,
            charged_magnet=True,
            charged_camera=True,
            charged_fire=True,
            financed_amount=financed_full,
            plan=selected_plan_full,
            tag="STANDARD",
        )
    )

# ---- RABATTERAT ERBJUDANDE (BJUSSA) ----

st.subheader("2️⃣ Rabatterat erbjudande (bjussa)")

discount_plan = None
discount_amount_total = 0.0
discount_percent_total = 0.0
discount_percent_extras = 0.0

if (
    (magnet_count or camera_count or fire_count)
    and (not charged_magnet or not charged_camera or not charged_fire)
):
    extras_charged = (
        (magnet_count * EXTRA_MAGNET if charged_magnet else 0)
        + (camera_count * EXTRA_CAMERA if charged_camera else 0)
        + (fire_count * EXTRA_FIRE if charged_fire else 0)
    )

    financed_discount = base_price + extras_charged + INSTALLATION_COST
    plans_discount = compute_plans(financed_discount)

    discount_plan, within_tol = choose_discount_plan_to_match_price(
        plans_discount, target_monthly=desired_monthly, tolerance=tolerance
    )

    discount_amount_total = (
        selected_plan_full["total"] - discount_plan["total"]
    )
    if selected_plan_full["total"] > 0:
        discount_percent_total = (
            discount_amount_total / selected_plan_full["total"]
        ) * 100

    extras_discount_value = extras_total_full - extras_charged
    if extras_total_full > 0:
        discount_percent_extras = (
            extras_discount_value / extras_total_full
        ) * 100

    cols_discount = st.columns(1 if mobile_mode else 2)

    with cols_discount[0]:
        st.markdown("**Rekommenderad rabatterad plan**")
        st.write(f"Plan: **{discount_plan['label']}**")
        st.write(
            f"💰 Månadskostnad: **{discount_plan['monthly']:.2f} kr/mån**"
        )
        st.write(
            f"⏱ Bindningstid: **{discount_plan['months']} månader**"
        )
        st.write(
            f"📦 Totalt inkl startavgift: **{discount_plan['total']:.2f} kr**"
        )

        if within_tol:
            st.success(
                f"Ligger inom ±{tolerance} kr från kundens önskade belopp "
                f"({desired_monthly:.0f} kr/mån)."
            )
        else:
            st.warning(
                "Ingen plan hamnade inom toleransen – visar närmaste möjliga mot kundens önskade belopp."
            )

        if discount_amount_total > 0:
            st.markdown(
                f"**Rabatt totalt:** cirka {discount_amount_total:.0f} kr "
                f"({discount_percent_total:.1f} % jämfört med standard)."
            )
        if extras_total_full > 0 and extras_discount_value > 0:
            st.markdown(
                f"**Rabatt på tillval:** cirka {extras_discount_value:.0f} kr "
                f"({discount_percent_extras:.1f} % av tillvalsvärdet)."
            )

        st.markdown("**Talking point till kund:**")
        st.write(
            f"\"Vi lägger oss runt **{discount_plan['monthly']:.0f} kr per månad**, "
            f"men jag bjuder på delar av utrustningen åt dig. "
            f"Bindningstiden blir **{discount_plan['months']} månader**, "
            f"och totalt landar det på ungefär **{discount_plan['total']:.0f} kr** inklusive startavgiften.\""
        )

    with cols_discount[-1]:
        st.markdown("**Alla planer (med rabatt)**")
        st.dataframe(
            {
                "Plan": [p["label"] for p in plans_discount],
                "Månader": [p["months"] for p in plans_discount],
                "kr/mån": [round(p["monthly"], 2) for p in plans_discount],
                "Totalt (kr)": [round(p["total"], 2) for p in plans_discount],
            },
            use_container_width=True,
        )

    with st.expander("Säljar-detaljer – Rabatt"):
        st.markdown(
            seller_breakdown(
                base_price,
                is_over_70,
                magnet_count,
                camera_count,
                fire_count,
                charged_magnet,
                charged_camera,
                charged_fire,
                financed_amount=financed_discount,
                plan=discount_plan,
                tag="RABATT",
            )
        )

else:
    st.info(
        "Inga tillval bjussas just nu. Välj tillval och kryssa i vad du bjuder på i sidomenyn för att se rabattläge."
    )

# ---- KONKURRENS & PROVISION ----

st.subheader("3️⃣ Konkurrentjämförelse & Provision")

offer_plan_for_calc = discount_plan or selected_plan_full

cols_cp = st.columns(1 if mobile_mode else 2)

with cols_cp[0]:
    st.markdown("**Konkurrentjämförelse – hyra vs STL med sänkt serviceavgift**")
    st.write(
        "Antagande:\n"
        "- **Konkurrenten:** hyrmodell – kunden betalar samma månadskostnad så länge larmet sitter uppe.\n"
        f"- **STL:** när larmet är avbetalat sjunker kostnaden till ca {SERVICE_MONTHLY:.0f} kr/mån "
        f"(≈ {SERVICE_HALF_YEAR:.0f} kr per halvår) för service/uppkoppling."
    )

    comp_monthly = st.number_input(
        "Konkurrentens månadskostnad (kr/mån)",
        min_value=0.0,
        value=0.0,
        step=50.0,
        key="comp_monthly",
    )
    comp_start = st.number_input(
        "Konkurrentens startavgift (kr)",
        min_value=0.0,
        value=0.0,
        step=100.0,
        key="comp_start",
    )

    if st.button("Beräkna långtidsjämförelse"):
        if offer_plan_for_calc is None:
            st.warning("Ingen plan att jämföra mot ännu – räkna fram ett erbjudande först.")
        else:
            horizons = [
                ("3 år", 36),
                ("5 år", 60),
                ("10 år", 120),
                ("15 år", 180),
            ]

            our_monthly = offer_plan_for_calc["monthly"]   # full kostnad under bindningstid
            our_months = offer_plan_for_calc["months"]     # bindningstid

            labels = []
            years = []
            our_costs = []
            comp_costs = []
            diffs = []

            for label, months in horizons:
                # STL total:
                months_full = min(months, our_months)
                cost_full = our_monthly * months_full
                months_service = max(0, months - our_months)
                cost_service = SERVICE_MONTHLY * months_service
                our_total = START_FEE + cost_full + cost_service

                # Konkurrent: hyrkoncept – samma månadskostnad hela perioden
                comp_total = comp_start + comp_monthly * months

                diff = comp_total - our_total

                labels.append(label)
                years.append(months / 12)
                our_costs.append(round(our_total, 2))
                comp_costs.append(round(comp_total, 2))
                diffs.append(round(diff, 2))

            st.markdown("**Totalkostnad över tid**")
            st.dataframe(
                {
                    "Period": labels,
                    "STL totalt (service efter avbetalning)": our_costs,
                    "Konkurrent totalt (hyra)": comp_costs,
                    "Skillnad (konk - STL)": diffs,
                },
                use_container_width=True,
            )

            st.markdown("**Graf – totalkostnad över tid**")
            df_graph_total = pd.DataFrame(
                {
                    "År": years,
                    "STL (totalt)": our_costs,
                    "Konkurrent (totalt)": comp_costs,
                }
            ).set_index("År")
            st.line_chart(df_graph_total)

            # Graf för att visa tydligt att STL sjunker till ~99 kr/mån
            st.markdown("**Graf – månadskostnad över tid**")
            years_monthly = list(range(1, 16))  # år 1–15
            stl_monthly_curve = []
            comp_monthly_curve = []
            for year in years_monthly:
                months_elapsed = year * 12
                if months_elapsed <= our_months:
                    stl_m = our_monthly
                else:
                    stl_m = SERVICE_MONTHLY
                stl_monthly_curve.append(round(stl_m, 2))
                comp_monthly_curve.append(round(comp_monthly, 2))

            df_graph_monthly = pd.DataFrame(
                {
                    "År": years_monthly,
                    "STL månadskostnad": stl_monthly_curve,
                    "Konkurrent månadskostnad": comp_monthly_curve,
                }
            ).set_index("År")
            st.line_chart(df_graph_monthly)

            st.write(
                "🔍 **Tolkning:**\n"
                "- Under bindningstiden betalar kunden full STL-månadskostnad, precis som hos konkurrenten.\n"
                f"- När larmet är avbetalat sjunker STL tydligt till ca {SERVICE_MONTHLY:.0f} kr/mån, "
                "medan konkurrenten fortsätter ta full hyra.\n"
                "- I månadsgrafen ser du hur STL-linjen droppar, medan konkurrentens linje ligger kvar högt.\n"
                "- Ju längre period (t.ex. 10–15 år), desto större blir skillnaden till STL:s fördel."
            )

with cols_cp[-1]:
    st.markdown("**Provision / bonus för denna affär**")
    if offer_plan_for_calc:
        # Merförsäljning = värdet av tillval kunden faktiskt betalar
        extras_charged_final = (
            (magnet_count * EXTRA_MAGNET if charged_magnet else 0)
            + (camera_count * EXTRA_CAMERA if charged_camera else 0)
            + (fire_count * EXTRA_FIRE if charged_fire else 0)
        )

        base_comm = BASE_COMMISSION_PER_DEAL
        upsell_comm = extras_charged_final * UPSELL_COMMISSION_RATE
        install_comm = INSTALLATION_COST * INSTALL_COMMISSION_RATE

        total_before_comp = base_comm + upsell_comm + install_comm

        # Kundkompensation: om något bjuds eller rabatterad plan används
        has_comp = (
            (magnet_count and not charged_magnet)
            or (camera_count and not charged_camera)
            or (fire_count and not charged_fire)
            or (discount_plan is not None)
        )

        if has_comp:
            total_after_comp = total_before_comp * (1 - COMPENSATION_PENALTY_RATE)
            comp_penalty = total_before_comp - total_after_comp
        else:
            total_after_comp = total_before_comp
            comp_penalty = 0.0

        mile_comp_total = miles_driven * MILE_COMP

        monthly_bonus = bonus_for_net_sales(int(net_sales_month))

        st.write(f"Grundprovision per sålt paket: **{base_comm:.0f} kr**")
        st.write(
            f"Merförsäljning (tillval debiterade: {extras_charged_final:.0f} kr) "
            f"→ 10% = **{upsell_comm:.0f} kr**"
        )
        st.write(
            f"Installationsprovision (20% av {INSTALLATION_COST:.0f} kr) = "
            f"**{install_comm:.0f} kr**"
        )

        if has_comp:
            st.write(
                f"Kundkompensation upptäckt → -20% av totala provisionen: "
                f"**-{comp_penalty:.0f} kr**"
            )

        st.write(
            f"Provision för denna affär (exkl milersättning): "
            f"**{total_after_comp:.0f} kr**"
        )

        st.write(
            f"Milersättning ({miles_driven:.1f} mil × {MILE_COMP:.2f} kr/mil): "
            f"**{mile_comp_total:.0f} kr**"
        )

        st.write(
            f"Total ersättning för denna affär inkl milersättning: "
            f"**{(total_after_comp + mile_comp_total):.0f} kr**"
        )

        st.markdown("---")
        st.write(
            f"Månadsbonusnivå vid {int(net_sales_month)} nettoförsäljningar: "
            f"**{monthly_bonus:.0f} kr**"
        )
        st.caption(
            "Bonusnivåerna går ej att kombinera – endast en nivå per månad enligt avtalet."
        )

    else:
        st.info(
            "Ingen plan att räkna provision på än – räkna först fram ett erbjudande ovan."
        )

# ---- EXPORT & KUNDPROFILER ----

st.subheader("4️⃣ Offert-text & Kundprofiler")

extras_charged_final_for_text = (
    (magnet_count * EXTRA_MAGNET if charged_magnet else 0)
    + (camera_count * EXTRA_CAMERA if charged_camera else 0)
    + (fire_count * EXTRA_FIRE if charged_fire else 0)
)

offer_text = generate_offer_text(
    customer_name,
    customer_phone,
    customer_address,
    customer_note,
    standard_plan=selected_plan_full,
    discount_plan=discount_plan,
    base_price=base_price,
    is_over_70=is_over_70,
    magnet_count=magnet_count,
    camera_count=camera_count,
    fire_count=fire_count,
    extras_total_full=extras_total_full,
    extras_charged=extras_charged_final_for_text,
    discount_amount_total=discount_amount_total,
    discount_percent_total=discount_percent_total,
    discount_percent_extras=discount_percent_extras,
)

cols_export = st.columns(1 if mobile_mode else 2)

with cols_export[0]:
    st.markdown("**Offert-text (för kopiering / sms / mail)**")
    st.text_area("Offert", offer_text, height=260)

with cols_export[-1]:
    if st.button("💾 Spara kundprofil"):
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "name": customer_name,
            "phone": customer_phone,
            "address": customer_address,
            "note": customer_note,
            "is_over_70": is_over_70,
            "base_price": base_price,
            "magnet_count": magnet_count,
            "camera_count": camera_count,
            "fire_count": fire_count,
            "monthly": (offer_plan_for_calc["monthly"] if offer_plan_for_calc else 0),
            "months": (offer_plan_for_calc["months"] if offer_plan_for_calc else 0),
            "total": (offer_plan_for_calc["total"] if offer_plan_for_calc else 0),
        }
        st.session_state.customers.append(record)
        save_customers(st.session_state.customers)
        st.success("Kundprofil sparad.")

    with st.expander("Sparade kunder"):
        if st.session_state.customers:
            st.dataframe(st.session_state.customers, use_container_width=True)
        else:
            st.write("Inga kunder sparade ännu.")
