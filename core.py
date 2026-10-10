"""Search and analysis logic for the demo (pure pandas, no database).

It mirrors what the Oracle version does: normalise the typed plate, find exact or one-edit-away matches,
order them in time, and compute minutes and speed between consecutive sightings.
"""
import re

import numpy as np
import pandas as pd

PLAZAS = {"A": 0, "B": 40, "C": 95, "D": 150}      # km marker along the demo highway
MAX_SPEED = 130                                    # km/h; faster than this is flagged as suspicious


def normalize(plate):
    return re.sub(r"[^A-Z0-9]", "", str(plate).upper())


def lev(a, b):
    """Levenshtein edit distance."""
    if a == b:
        return 0
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[-1]


def load(path):
    df = pd.read_csv(path, parse_dates=["seen_at"]).fillna({"plate_text": ""})
    df["km"] = df.plaza.map(PLAZAS)
    df["correct"] = df.plate_text == df.true_plate
    return df


def add_legs(r):
    """Minutes, speed and alert for every sighting compared with the previous one in the table."""
    r = r.sort_values(["seen_at", "plaza"]).reset_index(drop=True)
    r["minutes_since_prev"] = r.seen_at.diff().dt.total_seconds() / 60
    km_apart = r.km.diff().abs()
    with np.errstate(divide="ignore", invalid="ignore"):
        r["speed_kmh"] = np.where(r.minutes_since_prev > 0, km_apart / (r.minutes_since_prev / 60), np.nan)
    too_fast = r.speed_kmh > MAX_SPEED
    same_time = (r.minutes_since_prev <= 0) & (km_apart > 0)
    r["alert"] = np.where(too_fast, "faster than 130 km/h", np.where(same_time, "same time, two places", ""))
    return r


def find_route(df, plate, max_dist=1):
    """Sightings whose read plate is within max_dist edits of the typed plate, in time order."""
    q = normalize(plate)
    if len(q) < 4:
        raise ValueError("Please type at least 4 characters of the plate number.")
    if max_dist == 0:
        hit = df[df.plate_text == q]
    else:
        near = df.plate_text.str.len().sub(len(q)).abs() <= max_dist
        hit = df[near & df.plate_text.map(lambda p: lev(p, q) <= max_dist)]
    return add_legs(hit.copy())


def suspicious_legs(df):
    """Legs between consecutive sightings of the same read plate that no car could drive."""
    rows = []
    for plate, g in df[df.plate_text != ""].groupby("plate_text"):
        if len(g) < 2:
            continue
        g = add_legs(g.copy())
        for i in range(1, len(g)):
            if g.alert.iloc[i]:
                rows.append(dict(plate=plate, kind=g.kind.iloc[i], first_plaza=g.plaza.iloc[i - 1], second_plaza=g.plaza.iloc[i],
                                 first_seen=g.seen_at.iloc[i - 1], second_seen=g.seen_at.iloc[i],
                                 km_apart=abs(g.km.iloc[i] - g.km.iloc[i - 1]), minutes_apart=g.minutes_since_prev.iloc[i],
                                 speed_kmh=g.speed_kmh.iloc[i], why=g.alert.iloc[i]))
    return pd.DataFrame(rows)


def all_legs(df):
    """Every leg between consecutive sightings of the same read plate (used for the baseline statistics)."""
    out = []
    for plate, g in df[df.plate_text != ""].groupby("plate_text"):
        if len(g) >= 2:
            out.append(add_legs(g.copy()).iloc[1:])
    return pd.concat(out) if out else pd.DataFrame()


def reading_quality(df):
    rows = []
    for kind in ["tracked", "noise"]:
        s = df[df.kind == kind]
        d = np.array([lev(p, t) for p, t in zip(s.plate_text, s.true_plate)])
        rows.append({"events": kind, "photos": len(s), "exact read": (d == 0).mean(), "within 1 edit": (d <= 1).mean()})
    return pd.DataFrame(rows)


def search_quality(df):
    """Route recall and precision for every tracked car, exact vs fuzzy search."""
    tracked = df[df.kind == "tracked"]
    out = []
    for name, dist in [("Exact", 0), ("Fuzzy (up to 1 edit)", 1)]:
        tp = ret = tru = full = 0
        cars = tracked.true_plate.unique()
        for q in cars:
            true_ids = set(tracked[tracked.true_plate == q].event_no)
            hits = set(find_route(df[df.kind != "planted"], q, dist).event_no)
            t = len(hits & true_ids)
            tp += t; ret += len(hits); tru += len(true_ids); full += (t == len(true_ids))
        out.append({"search": name, "recall": tp / tru, "precision": tp / ret if ret else np.nan,
                    "cars with full route": full / len(cars), "cars": len(cars)})
    return pd.DataFrame(out)


def examples(df):
    """Interesting plates to try: cars the fuzzy search rescues, a clean car, and the cloned-plate test case."""
    tracked = df[df.kind == "tracked"]
    rows = []
    for q, g in tracked.groupby("true_plate"):
        rows.append((q, len(g), int((g.plate_text == q).sum())))
    t = pd.DataFrame(rows, columns=["plate", "sightings", "exact"])
    rescued = t[t.exact < t.sightings].sort_values(["sightings", "plate"], ascending=[False, True]).head(3)
    clean = t[t.exact == t.sightings].sort_values(["sightings", "plate"], ascending=[False, True]).head(1)
    clone = df[(df.kind == "planted")].groupby("true_plate").size()
    clone_plate = None
    for plate in clone.index:
        if not find_route(df, plate, 0).alert.eq("").all():
            clone_plate = plate
            break
    return {"rescued": rescued.plate.tolist(), "clean": clean.plate.tolist(), "clone": clone_plate}