"""Build the anonymized demo snapshot from the real pipeline output.

Run this on your laptop (it needs the original sightings.csv and ground_truth.csv, which are NOT part of the repo):

    python tools/build_snapshot.py  "C:/path/to/sightings.csv"  "C:/path/to/ground_truth.csv"

What it does
  * keeps only the columns the public demo needs (no image paths, no file names);
  * replaces every plate with a look-alike code using ONE random letter-for-letter and digit-for-digit
    substitution, applied to every read and every true plate. A one-to-one substitution keeps all edit
    distances identical, so exact and fuzzy search behave exactly as on the real data;
  * adds three clearly marked synthetic test cases (a cloned plate, a same-moment clone, a normal car);
  * discards the substitution table, so the output cannot be mapped back by this script.

This hides the real plate numbers from casual readers. It is not strong encryption.
"""
import secrets
import string
import sys
from datetime import datetime

import pandas as pd

PLANTED = [  # (event_no, time, plaza, plate)   synthetic test cases, kind = "planted"
    (9001, datetime(2026, 10, 9, 14, 0, 0), "A", "KA01AB1234"),
    (9002, datetime(2026, 10, 9, 14, 20, 0), "D", "KA01AB1234"),
    (9003, datetime(2026, 10, 9, 15, 0, 0), "B", "TN09CD5678"),
    (9004, datetime(2026, 10, 9, 15, 0, 0), "C", "TN09CD5678"),
    (9005, datetime(2026, 10, 9, 10, 0, 0), "A", "KA01AB9999"),
    (9006, datetime(2026, 10, 9, 10, 50, 0), "B", "KA01AB9999"),
]


def make_mapping(rng=None):
    rng = rng or secrets.SystemRandom()
    letters, digits = list(string.ascii_uppercase), list(string.digits)
    shuffled_l, shuffled_d = letters[:], digits[:]
    rng.shuffle(shuffled_l)
    rng.shuffle(shuffled_d)
    return dict(zip(letters + digits, shuffled_l + shuffled_d))


def anonymize(text, mapping):
    return "".join(mapping.get(c, c) for c in str(text).upper())


def build(sightings, truth, mapping):
    m = sightings.merge(truth[["event_no", "kind", "car_id", "truth"]], on="event_no", how="left")
    m["plate_text"] = m.plate_text.fillna("")
    out = pd.DataFrame({
        "event_no": m.event_no,
        "seen_at": pd.to_datetime(m.seen_at),
        "plaza": m.plaza,
        "plate_text": m.plate_text.map(lambda p: anonymize(p, mapping) if p else ""),
        "true_plate": m.truth.map(lambda p: anonymize(p, mapping)),
        "kind": m.kind,
        "car_id": m.car_id,
        "valid_format": m.valid_format,
        "det_conf": m.det_conf.round(4),
        "ocr_conf": m.ocr_conf.round(4),
    })
    extra = pd.DataFrame([{
        "event_no": e, "seen_at": t, "plaza": p,
        "plate_text": anonymize(plate, mapping), "true_plate": anonymize(plate, mapping),
        "kind": "planted", "car_id": f"P{e}", "valid_format": True, "det_conf": 0.9, "ocr_conf": 0.9,
    } for e, t, p, plate in PLANTED])
    return pd.concat([out, extra], ignore_index=True).sort_values("seen_at").reset_index(drop=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    s = pd.read_csv(sys.argv[1])
    g = pd.read_csv(sys.argv[2])
    snap = build(s, g, make_mapping())
    snap.to_csv("data/demo_snapshot.csv", index=False)
    print(f"Wrote data/demo_snapshot.csv with {len(snap)} rows "
          f"({(snap.kind == 'tracked').sum()} tracked, {(snap.kind == 'noise').sum()} noise, {(snap.kind == 'planted').sum()} planted)")