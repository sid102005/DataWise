"""Generate all test_data/ fixtures programmatically.

Run once:  python scripts/generate_test_data.py
"""
import pathlib
import random
import string

import pandas as pd
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "test_data"
DATA.mkdir(exist_ok=True)

rng = np.random.default_rng(42)

# ── basic_customers.csv ──────────────────────────────────────────────────────
customers = pd.DataFrame({
    "ID":      range(1, 11),
    "Name":    ["Alice", "Bob", "Charlie", "Diana", "Eve",
                "Frank", "Grace", "Hank", "Iris", "Jack"],
    "Email":   [f"user{i}@example.com" for i in range(1, 11)],
    "Address": [f"{i} Main St" for i in range(1, 11)],
    "Phone":   [f"555-{i:04d}" for i in range(1, 11)],
    "Age":     [25, 30, 35, 28, 42, 55, 33, 29, 47, 31],
    "City":    ["New York", "London", "Paris", "Berlin", "Tokyo",
                "Sydney", "Toronto", "Seoul", "Dubai", "Madrid"],
})
customers.to_csv(DATA / "basic_customers.csv", index=False)

# ── missing_values.csv ───────────────────────────────────────────────────────
missing = pd.DataFrame({
    "ID":     range(1, 11),
    "Name":   ["Alice", None, "Charlie", "Diana", None,
               "Frank", "Grace", None, "Iris", "Jack"],
    "Score":  [85.0, 92.0, None, 78.0, 88.0, None, 95.0, 70.0, None, 83.0],
    "Grade":  ["A", "A", "B", None, "B", "A", None, "C", "B", "A"],
})
missing.to_csv(DATA / "missing_values.csv", index=False)

# ── duplicates.csv ────────────────────────────────────────────────────────────
base = pd.DataFrame({
    "ID":    [1, 2, 3, 4, 5],
    "Name":  ["Alice", "Bob", "Charlie", "Diana", "Eve"],
    "Value": [100, 200, 300, 400, 500],
})
dupes = pd.concat([base, base.iloc[[0, 2]]], ignore_index=True)
dupes.to_csv(DATA / "duplicates.csv", index=False)

# ── numeric_data.csv ──────────────────────────────────────────────────────────
numeric = pd.DataFrame({
    "Product": [f"Item_{i}" for i in range(1, 21)],
    "Price":   rng.uniform(5.0, 500.0, 20).round(2),
    "Quantity": rng.integers(1, 100, 20).tolist(),
    "Discount": rng.uniform(0.0, 0.5, 20).round(3),
})
numeric["Total"] = (numeric["Price"] * numeric["Quantity"] * (1 - numeric["Discount"])).round(2)
numeric.to_csv(DATA / "numeric_data.csv", index=False)

# ── dates.csv ─────────────────────────────────────────────────────────────────
import datetime
dates_list = [
    (datetime.date(2023, 1, 1) + datetime.timedelta(days=int(d))).strftime(fmt)
    for d, fmt in zip(
        rng.integers(0, 365, 10),
        ["%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y",
         "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"],
    )
]
dates_df = pd.DataFrame({
    "ID":    range(1, 11),
    "Event": [f"Event_{i}" for i in range(1, 11)],
    "Date":  dates_list,
    "Value": rng.integers(100, 1000, 10).tolist(),
})
dates_df.to_csv(DATA / "dates.csv", index=False)

# ── larger_dataset.csv ────────────────────────────────────────────────────────
N = 150_000
regions = ["North", "South", "East", "West", "Central"]
categories = ["Electronics", "Clothing", "Food", "Furniture", "Toys"]
larger = pd.DataFrame({
    "OrderID":   range(1, N + 1),
    "CustomerID": rng.integers(1000, 9999, N).tolist(),
    "Region":    rng.choice(regions, N).tolist(),
    "Category":  rng.choice(categories, N).tolist(),
    "Sales":     rng.uniform(10.0, 5000.0, N).round(2),
    "Quantity":  rng.integers(1, 50, N).tolist(),
    "Profit":    rng.uniform(-500.0, 2000.0, N).round(2),
})
# Inject ~2% nulls in Sales and ~1% duplicates
null_idx = rng.choice(N, size=int(N * 0.02), replace=False)
larger.loc[null_idx, "Sales"] = None
dup_rows = larger.iloc[rng.choice(min(1000, N), size=int(N * 0.01), replace=True)]
larger = pd.concat([larger, dup_rows], ignore_index=True)
larger.to_csv(DATA / "larger_dataset.csv", index=False)

print("Test data generated:")
for f in sorted(DATA.iterdir()):
    rows = pd.read_csv(f).shape[0] if f.suffix == ".csv" else "?"
    print(f"  {f.name:30s} {rows:>8} rows")
