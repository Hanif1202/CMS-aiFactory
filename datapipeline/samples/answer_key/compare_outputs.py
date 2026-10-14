"""
compare_outputs.py  (ANSWER KEY)
Compares the agent's output CSVs to the reference outputs in expected_output/.

The agent's pipeline must produce the three output tables defined in target_spec.md.
Point this script at the folder holding the agent's CSVs:

    python compare_outputs.py path/to/agent_output_dir

Checks per table: column names, row count, key match, and cell values
(numbers within 0.01, text exact). run_timestamp is ignored.
Exit code 0 = all tables match, 1 = differences found.
"""
import sys
from pathlib import Path

import pandas as pd

EXPECTED_DIR = Path(__file__).with_name("expected_output")
TABLES = {
    "claim_detail": ["claim_id"],
    "provider_monthly_summary": ["npi", "report_month", "claim_category"],
    "claim_exceptions": ["claim_id"],
}
IGNORE = {"run_timestamp"}
TOL = 0.01


def load(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def compare(name, keys, actual_dir):
    exp = load(EXPECTED_DIR / f"{name}.csv")
    act_path = Path(actual_dir) / f"{name}.csv"
    if not act_path.exists():
        return [f"missing file {act_path.name}"]
    act = load(act_path)
    issues = []
    exp_cols = [c for c in exp.columns if c not in IGNORE]
    missing = [c for c in exp_cols if c not in act.columns]
    extra = [c for c in act.columns if c not in exp.columns]
    if missing:
        issues.append(f"missing columns {missing}")
    if extra:
        issues.append(f"unexpected columns {extra}")
    if missing:
        return issues
    if len(act) != len(exp):
        issues.append(f"row count {len(act)} vs expected {len(exp)}")

    merged = exp[exp_cols].merge(act[exp_cols], on=keys, how="outer",
                                 suffixes=("_exp", "_act"), indicator=True)
    for side, label in (("left_only", "missing row"), ("right_only", "unexpected row")):
        for _, r in merged[merged["_merge"] == side].iterrows():
            issues.append(f"{label}: {dict((k, r[k]) for k in keys)}")

    both = merged[merged["_merge"] == "both"]
    for col in [c for c in exp_cols if c not in keys]:
        for _, r in both.iterrows():
            e, a = r[f"{col}_exp"], r[f"{col}_act"]
            try:
                same = abs(float(e) - float(a)) <= TOL if (e or a) else True
            except ValueError:
                same = e == a
            if not same:
                issues.append(f"{dict((k, r[k]) for k in keys)} {col}: expected '{e}', got '{a}'")
    return issues


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    all_ok = True
    for name, keys in TABLES.items():
        issues = compare(name, keys, sys.argv[1])
        status = "PASS" if not issues else f"FAIL ({len(issues)} differences)"
        print(f"{name:<28} {status}")
        for i in issues[:25]:
            print(f"    - {i}")
        if len(issues) > 25:
            print(f"    ... {len(issues) - 25} more")
        all_ok &= not issues
    print("\nRESULT:", "ALL TABLES MATCH" if all_ok else "DIFFERENCES FOUND")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
