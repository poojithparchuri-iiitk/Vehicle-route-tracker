import os
from datetime import datetime

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import core

REPO_URL = ""     # paste your GitHub repository URL here to show a "View code" button
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "demo_snapshot.csv")
MODES = ["Exact", "Fuzzy (up to 1 character different)"]

st.set_page_config(page_title="Vehicle Route Tracker", page_icon="🚗", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2.2rem; max-width: 1180px;}
.hero {background: linear-gradient(135deg, #0b3d91 0%, #1f6feb 100%); color: #fff;
       padding: 1.5rem 1.8rem; border-radius: 14px; margin-bottom: 1.2rem;}
.hero h1 {margin: 0; font-size: 2rem; color: #fff; padding: 0;}
.hero p {margin: .45rem 0 0 0; opacity: .93; font-size: 1.02rem;}
.cards {display: flex; flex-wrap: wrap; gap: .6rem; margin: .4rem 0 1rem 0;}
.card {flex: 1 1 130px; border: 1px solid #dfe5ee; border-radius: 10px; padding: .55rem .85rem; background: #fff;}
.card .lbl {font-size: .8rem; color: #6b7685;}
.card .val {font-size: 1.45rem; font-weight: 600; color: #1b2430; white-space: nowrap;}
button[data-baseweb="tab"] p {font-size: 1.05rem;}
.notice {background: #fff8e1; border-left: 4px solid #f2b705; color: #3d3200;
         padding: .5rem .8rem; border-radius: 6px; font-size: .86rem; margin: 0 0 .8rem 0;}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def get_data():
    return core.load(DATA)


@st.cache_data
def get_examples():
    return core.examples(get_data())


@st.cache_data
def get_reading_quality():
    return core.reading_quality(get_data())


@st.cache_data
def get_search_quality():
    return core.search_quality(get_data())


@st.cache_data
def get_suspicious():
    return core.suspicious_legs(get_data())


@st.cache_data
def get_legs():
    return core.all_legs(get_data()[lambda d: d.kind != "planted"])


def hero(title, subtitle):
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def pct(x):
    return "" if pd.isna(x) else f"{100 * x:.1f}%"


def fmt_minutes(m):
    m = int(round(m))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"


def blank_nan(v):
    return "" if pd.isna(v) else f"{v:.0f}"


def cards(items):
    html = "".join(f'<div class="card"><div class="lbl">{label}</div><div class="val">{value}</div></div>' for label, value in items)
    st.markdown(f'<div class="cards">{html}</div>', unsafe_allow_html=True)


def log_search(plate, dist, found):
    st.session_state.setdefault("audit", []).append(
        {"time": datetime.now().strftime("%H:%M:%S"), "plate": core.normalize(plate), "max edits": dist, "sightings found": found})


def route_chart(r):
    r = r.copy()
    r["status"] = np.where(r.correct, "Read correctly", "Misread")
    r["time_label"] = r.seen_at.dt.strftime("%H:%M")
    r["speed_label"] = r.speed_kmh.map(lambda v: "" if pd.isna(v) else f"{v:.0f} km/h")
    base_y = alt.Y("km:Q", title="Distance along the highway (km)", scale=alt.Scale(domain=[-8, 160]))
    plazas = pd.DataFrame({"km": list(core.PLAZAS.values()), "label": [f"Plaza {p}" for p in core.PLAZAS]})
    grid = alt.Chart(plazas).mark_rule(strokeDash=[4, 4], color="#c5cdd9").encode(y="km:Q")
    names = alt.Chart(plazas).mark_text(align="left", dx=4, dy=-7, color="#6b7685", fontSize=12).encode(
        y="km:Q", text="label:N", x=alt.value(4))
    layers = [grid, names]
    if len(r) > 1:
        legs = pd.DataFrame({
            "t1": r.seen_at.shift(), "t2": r.seen_at, "km1": r.km.shift(), "km2": r.km,
            "bad": (r.alert != "").values,
        }).iloc[1:]
        layers.append(alt.Chart(legs).mark_rule(strokeWidth=3).encode(
            x="t1:T", x2="t2:T", y="km1:Q", y2="km2:Q",
            color=alt.condition("datum.bad", alt.value("#d1242f"), alt.value("#1f6feb"))))
    points = alt.Chart(r).mark_point(size=130, filled=True, opacity=1).encode(
        x=alt.X("seen_at:T", title="Time of day", axis=alt.Axis(format="%H:%M")),
        y=base_y,
        color=alt.Color("status:N", title=None,
                        scale=alt.Scale(domain=["Read correctly", "Misread"], range=["#1a7f37", "#e0821b"])),
        tooltip=[alt.Tooltip("plaza:N", title="Plaza"), alt.Tooltip("time_label:N", title="Time"),
                 alt.Tooltip("plate_text:N", title="Plate read"), alt.Tooltip("speed_label:N", title="Speed")])
    layers.append(points)
    return alt.layer(*layers).properties(height=340)


# ------------------------------------------------------------------ pages
def search_page(df):
    hero("Where did this vehicle go?",
         "Choose a match type, type a plate number and press Search to see the toll plazas it crossed, in order. "
         "Fuzzy matching still finds the vehicle when the plate reader made a mistake.")
    ex = get_examples()

    if "plate" not in st.session_state:
        st.session_state.plate = ex["rescued"][0] if ex["rescued"] else ""
    if "mode" not in st.session_state:
        st.session_state.mode = MODES[1]

    def run_query():
        plate, mode = st.session_state.plate, st.session_state.mode
        st.session_state.query = (plate, mode)
        try:
            found = len(core.find_route(get_data(), plate, 0 if mode == MODES[0] else 1))
        except ValueError:
            return
        log_search(plate, 0 if mode == MODES[0] else 1, found)

    with st.form("search_form"):
        st.radio("Match type", MODES, key="mode", horizontal=True)
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        c1.text_input("Plate number", key="plate", max_chars=15)
        c2.form_submit_button("Search", type="primary", on_click=run_query)

    q = st.session_state.get("query")
    if q is None:
        st.info("Press Search to see the route.")
        return
    plate, mode = q
    dist = 0 if mode == MODES[0] else 1
    try:
        exact = core.find_route(df, plate, 0)
        fuzzy = core.find_route(df, plate, 1)
    except ValueError as e:
        st.info(str(e))
        return
    r = exact if dist == 0 else fuzzy

    st.markdown(f"Results for **{core.normalize(plate)}** with **{mode.split(' (')[0].lower()}** matching")
    if r.empty:
        st.warning("No sightings found for this plate. Check the plate number, or switch to fuzzy matching.")
        return
    if dist == 1 and len(fuzzy) > len(exact):
        st.success(f"Exact search finds {len(exact)} sighting(s). Fuzzy matching finds {len(fuzzy)}: "
                   f"{len(fuzzy) - len(exact)} more where the plate reader misread a character.")
    elif dist == 0 and len(fuzzy) > len(exact):
        st.info(f"Exact search finds {len(exact)} sighting(s). Switch to fuzzy matching to see "
                f"{len(fuzzy) - len(exact)} more where the plate was misread.")
    if (r.alert != "").any():
        st.error("This route contains a leg that no car could drive (too fast, or two places at once). "
                 "The plate may be cloned or misread.")

    span = (r.seen_at.iloc[-1] - r.seen_at.iloc[0]).total_seconds() / 60
    cards([("Sightings", len(r)), ("Plazas", r.plaza.nunique()),
           ("Distance", f"{abs(r.km.iloc[-1] - r.km.iloc[0]):.0f} km"),
           ("Duration", fmt_minutes(span) if len(r) > 1 else "-"),
           ("Top speed", f"{r.speed_kmh.max():.0f} km/h" if r.speed_kmh.notna().any() else "-")])

    st.subheader("Route in time order")
    show = pd.DataFrame({
        "Plaza": r.plaza,
        "Time": r.seen_at.dt.strftime("%H:%M"),
        "Plate read": r.plate_text,
        "Reader check": np.where(r.correct, "correct", "misread (true: " + r.true_plate + ")"),
        "Reader confidence": r.ocr_conf,
        "Min since previous": r.minutes_since_prev.map(blank_nan),
        "km/h": r.speed_kmh.map(blank_nan),
        "Alert": r.alert,
    })
    st.dataframe(show, hide_index=True, column_config={
        "Reader confidence": st.column_config.ProgressColumn("Reader confidence", min_value=0.0, max_value=1.0, format="%.2f")})
    st.caption("The demo knows the true plate because the data is simulated, so it can mark each read as correct or misread.")

    st.subheader("Distance along the highway over time")
    st.altair_chart(route_chart(r))
    st.caption("Blue lines are normal legs and red lines are impossible ones. Green dots are correct reads, orange dots are misreads.")


def dashboard_page(df):
    hero("Dashboard", "What the system saw in the simulated day, and how well it read and searched.")
    d = df[df.kind != "planted"]
    cards([("Photos processed", len(d)), ("Tracked cars", d[d.kind == "tracked"].true_plate.nunique()),
           ("Plazas", d.plaza.nunique()), ("Misread plates", int((~d.correct).sum()))])

    c1, c2 = st.columns(2)
    c1.subheader("Photos per plaza")
    c1.bar_chart(d.plaza.value_counts().sort_index())
    c2.subheader("Photos per hour")
    c2.bar_chart(d.seen_at.dt.strftime("%H:00").value_counts().sort_index())

    st.subheader("How well does the plate reader do?")
    q = get_reading_quality().copy()
    q["exact read"] = q["exact read"].map(pct)
    q["within 1 edit"] = q["within 1 edit"].map(pct)
    st.dataframe(q, hide_index=True)
    st.caption("Tracked = photos of the 20 cars that visit several plazas. Noise = one-off cars. "
               "Within 1 edit means one wrong, missing or extra character.")

    st.subheader("How well does the route search do?")
    s = get_search_quality().copy()
    for col in ["recall", "precision", "cars with full route"]:
        s[col] = s[col].map(pct)
    st.dataframe(s, hide_index=True)
    st.caption("Recall = share of a car's true sightings that the search finds. Precision = share of returned sightings that really are that car. "
               "Precision is high here because the one-off cars are all different, so treat it as a small-sample result.")

    st.subheader("Does reader confidence reveal mistakes?")
    rows = []
    for t in (0.8, 0.9, 0.95):
        low = d[d.ocr_conf < t]
        rows.append({"reader confidence below": t, "reads": len(low), "of which misread": int((~low.correct).sum()),
                     "misreads caught": f"{(~low.correct).sum()} of {(~d.correct).sum()}"})
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption("A low confidence is a reliable warning, but many wrong reads are confidently wrong, so confidence alone cannot find them. "
               "That is why the search tolerates one wrong character.")

    st.subheader("Your searches in this session")
    log = st.session_state.get("audit", [])
    if log:
        st.dataframe(pd.DataFrame(log[::-1]), hide_index=True)
    else:
        st.caption("No searches yet. In the Oracle version every search is stored in an audit table.")


def suspicious_page(df):
    hero("Suspicious travel",
         "Legs between two sightings of the same plate that no car could drive: faster than "
         f"{core.MAX_SPEED} km/h, or two different plazas at the same moment.")
    legs = get_legs()
    sus = get_suspicious()
    real_sus = sus[sus.kind != "planted"] if len(sus) else sus
    cards([("Legs checked in the data", len(legs)), ("Flagged in the data", len(real_sus)),
           ("Synthetic test cases flagged", int((sus.kind == "planted").sum()) if len(sus) else 0)])
    if len(legs):
        st.caption(f"Speeds between consecutive sightings of the same plate in the data: lowest {legs.speed_kmh.min():.0f}, "
                   f"median {legs.speed_kmh.median():.0f}, highest {legs.speed_kmh.max():.0f} km/h.")
    if len(sus):
        show = pd.DataFrame({
            "Plate": sus.plate,
            "Source": np.where(sus.kind == "planted", "synthetic test case", "data"),
            "From": sus.first_plaza + " " + sus.first_seen.dt.strftime("%H:%M"),
            "To": sus.second_plaza + " " + sus.second_seen.dt.strftime("%H:%M"),
            "km apart": sus.km_apart.map(blank_nan),
            "Minutes apart": sus.minutes_apart.map(blank_nan),
            "km/h": sus.speed_kmh.map(blank_nan),
            "Why": sus.why,
        })
        st.dataframe(show, hide_index=True)
    st.info("Two cases were added on purpose to show the check working: a plate seen 150 km apart 20 minutes later, and a plate at "
            "two plazas at the same moment. A normal car (40 km in 50 minutes) is correctly not flagged.")
    st.markdown("**Limits of this check:** it only compares reads that are identical text, so a clone whose plate was misread at one "
                "plaza would look like a different car. The 130 km/h limit is a chosen threshold, set above the fastest speed in the "
                "data. With 34 legs it is a demonstration, not a measured detection rate.")


def how_page(df):
    hero("How it works", "From a photo at a toll plaza to a searchable route, and what was measured along the way.")
    st.graphviz_chart("""
    digraph G {
      rankdir=LR; bgcolor="transparent";
      node [shape=box, style="rounded,filled", fillcolor="#eaf2ff", color="#1f6feb", fontname="Helvetica", fontsize=11];
      edge [color="#6b7685"];
      photo [label="Photo at a plaza\\n(timed feed)"];
      det   [label="YOLOv8s\\nplate detector"];
      crop  [label="Plate crop"];
      ocr   [label="Fine-tuned TrOCR\\nplate reader"];
      db    [label="Oracle database\\nsightings + audit log", fillcolor="#fff1e0", color="#e0821b"];
      search[label="Exact / fuzzy\\nroute search"];
      chk   [label="Impossible-travel\\ncheck (SQL LAG)"];
      ui    [label="Web page", fillcolor="#e7f6ec", color="#1a7f37"];
      photo -> det -> crop -> ocr -> db;
      db -> search -> ui;
      db -> chk -> ui;
    }""")
    st.caption("This public page runs on an anonymized snapshot of the results, searched with pandas. The full version stores the same "
               "results in Oracle and searches them with a PL/SQL procedure.")

    st.subheader("Measured results")
    st.markdown("**Plate detector** (YOLOv8s, trained on 1,034 images, tested on cars it never saw)")
    st.dataframe(pd.DataFrame([
        {"Test set": "Test split (139 images)", "Precision": 0.985, "Recall": 0.978, "mAP50": 0.993},
        {"Test set": "Held-out tracked cars (180 images)", "Precision": 0.981, "Recall": 0.989, "mAP50": 0.992}]), hide_index=True)
    st.markdown("**Plate reader** (same 180 photos of 40 held-out cars, detector crops)")
    st.dataframe(pd.DataFrame([
        {"Reader": "EasyOCR (off the shelf)", "Exact plate": "14.4%", "Within 1 edit": "30.0%", "Character accuracy": "66.4%"},
        {"Reader": "TrOCR fine-tuned on the training plates", "Exact plate": "86.7%", "Within 1 edit": "95.0%", "Character accuracy": "97.1%"}]),
        hide_index=True)
    st.markdown("**Database benchmarks** (Oracle Free in Docker, 1,000,000 synthetic sightings, one laptop)")
    st.dataframe(pd.DataFrame([
        {"Test": "Plate lookup, composite (plate, time) index", "Before": "about 29 to 35 ms", "After": "about 3 ms", "Result": "about 10x faster"},
        {"Test": "Fuzzy search (1 edit), prefix/suffix covering indexes", "Before": "about 4.1 s", "After": "about 27 ms", "Result": "about 150x faster, identical results"},
        {"Test": "Daily partitioning for date queries", "Before": "full scan 68 ms", "After": "partitioned 78 ms (index: 6 ms)", "Result": "no speedup; the index won"}]),
        hide_index=True)
    st.caption("Dropping 7 daily partitions took 18 s against 1.9 s for a plain DELETE. I did not find out why.")

    st.subheader("Limits to keep in mind")
    st.markdown("""
- The cars, plazas, routes and times are **simulated**. The photos are a public web-scraped dataset, not real toll-plaza footage.
- Accuracy figures come from small sets (40 held-out cars, many near-duplicate photos), so read them as "about", not as exact.
- About 40% of the plates in the training data are Maharashtra plates, so other states are covered less.
- The route-search precision is measured against a small set of unrelated one-off cars. A large database with many look-alike plates would show more wrong matches with fuzzy search.
- Plate numbers on this page are anonymized: every read and every true plate was passed through one random letter-for-letter and digit-for-digit substitution, which keeps all edit distances the same. It hides the real numbers; it is not strong encryption.
""")
    if REPO_URL:
        st.link_button("View the code on GitHub", REPO_URL)


df = get_data()

head, link = st.columns([5, 1], vertical_alignment="center")
head.markdown("## Vehicle Route Tracker")
if REPO_URL:
    link.link_button("View code on GitHub", REPO_URL)
st.markdown('<div class="notice"><b>Demo data.</b> An anonymized snapshot of a simulated day at four toll plazas. '
            'Plates are replaced by look-alike codes.</div>', unsafe_allow_html=True)

tab_search, tab_dash, tab_susp, tab_how = st.tabs(["Route search", "Dashboard", "Suspicious travel", "How it works"])
with tab_search:
    search_page(df)
with tab_dash:
    dashboard_page(df)
with tab_susp:
    suspicious_page(df)
with tab_how:
    how_page(df)