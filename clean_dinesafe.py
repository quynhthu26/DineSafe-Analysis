"""
Dinesafe Data Cleaning Script
==============================
Cleans Dinesafe.csv and produces Dinesafe_cleaned.csv.

Cleaning decisions documented inline.
Run with: python3 clean_dinesafe.py
"""

import pandas as pd
import re
import sys
from pathlib import Path

INPUT  = Path(__file__).parent / "Dinesafe.csv"
OUTPUT = Path(__file__).parent / "Dinesafe_cleaned.csv"

# ── 1. Load ────────────────────────────────────────────────────────────────
print("Loading data...")
df = pd.read_csv(INPUT, low_memory=False)

shape_before = df.shape
print(f"  Loaded: {shape_before[0]:,} rows × {shape_before[1]} columns")

changes = []   # accumulate summary messages

# ── 2. Drop fully-empty columns ────────────────────────────────────────────
all_null_cols = [c for c in df.columns if df[c].isna().all()]
if all_null_cols:
    df.drop(columns=all_null_cols, inplace=True)
    changes.append(f"Dropped {len(all_null_cols)} fully-null column(s): {all_null_cols}")
else:
    changes.append("No fully-null columns found.")

# ── 3. Drop `_id` (pure sequential row-counter, adds no information) ───────
if "_id" in df.columns:
    df.drop(columns=["_id"], inplace=True)
    changes.append("Dropped `_id`: was just a sequential row counter (1…N), not a domain key.")

# ── 4. Remove exact duplicate rows ─────────────────────────────────────────
n_before_dedup = len(df)
df.drop_duplicates(inplace=True)
df.reset_index(drop=True, inplace=True)
n_dupes = n_before_dedup - len(df)
changes.append(f"Removed {n_dupes:,} exact duplicate row(s).")

# ── 5. Strip leading/trailing whitespace from ALL string columns ────────────
str_cols = df.select_dtypes(include="object").columns.tolist()
for col in str_cols:
    df[col] = df[col].str.strip()
changes.append(f"Stripped leading/trailing whitespace from {len(str_cols)} text column(s).")

# ── 6. Standardise `Establishment Name` → Title Case ───────────────────────
# The column contains a mix of ALL-CAPS and Title-Case names.  Normalising to
# Title Case makes sorting, matching, and display consistent.
if "Establishment Name" in df.columns:
    df["Establishment Name"] = df["Establishment Name"].str.title()
    changes.append("Normalised `Establishment Name` to Title Case (was a mix of ALL-CAPS and mixed case).")

# ── 7. Standardise `Establishment Type` → Title Case ───────────────────────
if "Establishment Type" in df.columns:
    df["Establishment Type"] = df["Establishment Type"].str.title()
    changes.append("Normalised `Establishment Type` to Title Case.")

# ── 8. Standardise `Establishment Status` → Title Case ─────────────────────
# Values seen: Pass, Conditional Pass, Closed
if "Establishment Status" in df.columns:
    df["Establishment Status"] = df["Establishment Status"].str.title()
    changes.append("Normalised `Establishment Status` to Title Case.")

# ── 9. Standardise `Severity` → strip (values already consistent) ──────────
# Values: 'M - Minor', 'C - Crucial', 'S - Significant', 'NA - Not Applicable'
# Whitespace already stripped in step 5; no further change needed.

# ── 10. Standardise `Action` → strip (whitespace already handled in step 5)

# ── 11. Standardise `Outcome` → strip (whitespace already handled in step 5)

# ── 12. Fix `Min. Inspections Per Year` ─────────────────────────────────────
# Found at least one cell with the letter 'O' instead of the digit '0'.
if "Min. Inspections Per Year" in df.columns:
    raw = df["Min. Inspections Per Year"].astype(str)
    # Replace letter-O with zero, then coerce to numeric
    raw = raw.str.replace(r"\bO\b", "0", regex=True)
    converted = pd.to_numeric(raw, errors="coerce")
    n_bad = converted.isna().sum() - df["Min. Inspections Per Year"].isna().sum()
    df["Min. Inspections Per Year"] = converted
    if n_bad > 0:
        changes.append(
            f"Fixed `Min. Inspections Per Year`: replaced letter 'O' with 0; "
            f"{n_bad} cell(s) could not be parsed (left as NaN)."
        )
    else:
        changes.append("Converted `Min. Inspections Per Year` to numeric (fixed letter-'O' typo).")

# ── 13. Parse `Inspection Date` → datetime, output as ISO-8601 date ─────────
# Column already appears in YYYY-MM-DD format but may be stored as object.
if "Inspection Date" in df.columns:
    n_before_parse = df["Inspection Date"].isna().sum()
    df["Inspection Date"] = pd.to_datetime(df["Inspection Date"], errors="coerce")
    n_after_parse = df["Inspection Date"].isna().sum()
    n_unparseable = n_after_parse - n_before_parse
    # Format back to YYYY-MM-DD string for CSV output
    df["Inspection Date"] = df["Inspection Date"].dt.strftime("%Y-%m-%d")
    if n_unparseable > 0:
        changes.append(
            f"Parsed `Inspection Date` to datetime then formatted as YYYY-MM-DD. "
            f"{n_unparseable} value(s) could not be parsed (set to NaT/empty)."
        )
    else:
        changes.append("Parsed `Inspection Date` to datetime and formatted as YYYY-MM-DD (all values valid).")

# ── 14. Clean `Amount Fined` → float ────────────────────────────────────────
# Remove any currency symbols / commas / spaces, then coerce to float.
# Decision: leave genuinely missing fines as NaN (absence of fine ≠ 0).
# The value 0 means a fine was levied but at $0; NaN means no fine record.
if "Amount Fined" in df.columns:
    raw_fined = df["Amount Fined"].astype(str).str.strip()
    raw_fined = raw_fined.str.replace(r"[\$,\s]", "", regex=True)
    raw_fined = raw_fined.replace({"nan": None, "": None})
    df["Amount Fined"] = pd.to_numeric(raw_fined, errors="coerce")
    n_fined = df["Amount Fined"].notna().sum()
    changes.append(
        f"Cleaned `Amount Fined`: removed currency symbols/commas, converted to float. "
        f"{n_fined:,} non-null fine records."
    )

# ── 15. Handle remaining missing values ──────────────────────────────────────
# Columns with expected nulls:
#   Infraction Details  → null = no infraction found during inspection (valid)
#   Severity            → null when no infraction (valid)
#   Action              → null when no infraction (valid)
#   Outcome             → null when no fine/outcome recorded (valid)
#   Amount Fined        → null when no fine issued (valid, kept as NaN)
#   Inspection ID       → a small number of rows lack an Inspection ID;
#                         these appear to be establishments with no recent
#                         inspection on record.  Keep as NaN rather than dropping.
#
# Decision: We do NOT drop rows for missing Infraction Details / Severity / Action.
# These nulls encode real domain information (clean inspections).
# We DO document the null counts below.

null_summary = df.isnull().sum()
null_summary = null_summary[null_summary > 0].sort_values(ascending=False)
changes.append(
    "Missing-value policy: nulls in Infraction Details / Severity / Action / "
    "Outcome / Amount Fined represent 'no infraction / no fine' — preserved as NaN. "
    "Null Inspection IDs preserved (establishments with no recent recorded inspection)."
)

# ── 16. Reset index ──────────────────────────────────────────────────────────
df.reset_index(drop=True, inplace=True)

# ── 17. Save ─────────────────────────────────────────────────────────────────
df.to_csv(OUTPUT, index=False)
print(f"\nSaved cleaned file → {OUTPUT}")

# ── 18. Print summary ────────────────────────────────────────────────────────
shape_after = df.shape
print("\n" + "="*70)
print("CLEANING SUMMARY")
print("="*70)
print(f"  Rows  before: {shape_before[0]:,}   →   after: {shape_after[0]:,}  "
      f"(removed {shape_before[0] - shape_after[0]:,})")
print(f"  Cols  before: {shape_before[1]}        →   after: {shape_after[1]}    "
      f"(removed {shape_before[1] - shape_after[1]})")
print()
for i, msg in enumerate(changes, 1):
    print(f"  {i:2}. {msg}")
print()
print("Remaining null counts per column:")
if null_summary.empty:
    print("  (none)")
else:
    for col, cnt in null_summary.items():
        pct = cnt / shape_after[0] * 100
        print(f"  {col:<40} {cnt:>7,}  ({pct:.1f}%)")
print("="*70)
print("\nDone.")
