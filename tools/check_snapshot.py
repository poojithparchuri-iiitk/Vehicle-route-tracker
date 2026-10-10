import sys

import pandas as pd

s = pd.read_csv(sys.argv[1])
g = pd.read_csv(sys.argv[2])
snap = pd.read_csv("data/demo_snapshot.csv")

real = set(s.plate_text.dropna().astype(str)) | set(g.truth.astype(str))
shown = set(snap.plate_text.fillna("").astype(str)) | set(snap.true_plate.astype(str))
overlap = (real & shown) - {""}
print("real plate strings:", len(real), "| plate strings in the snapshot:", len(shown))
print("real plates that appear unchanged in the snapshot:", len(overlap), sorted(overlap)[:5])

text = open("data/demo_snapshot.csv", encoding="utf-8").read()
print("image paths or file names in the snapshot:", any(k in text for k in ["/content", ".jpg", ".png", "img0", "crop"]))
print("columns:", list(snap.columns))