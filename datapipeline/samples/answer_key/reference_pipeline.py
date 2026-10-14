"""
reference_pipeline.py  (ANSWER KEY - do not share with the agent)

Reference implementation of the target pipeline described in target_spec.md.
Reads the new-system tables from new.db and produces:
    claim_detail              one row per included claim, with calculated columns
    provider_monthly_summary  provider / month / category aggregates
    claim_exceptions          one row per excluded claim, with a reason code

Usage:  python reference_pipeline.py [--config config.yaml]
"""
import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

log = logging.getLogger("provider_summary")

REQUIRED_CLAIM_COLUMNS = [
    "claim_id", "npi", "beneficiary_id", "facility_type_code", "bill_classification_code",
    "claim_frequency_code", "service_from_date", "service_through_date", "received_date",
    "billed_amount", "allowed_amount", "deductible_amount", "coinsurance_amount", "status_code",
]
AMOUNT_COLUMNS = ["billed_amount", "allowed_amount", "deductible_amount", "coinsurance_amount"]


class PipelineError(Exception):
    """Raised when input data fails validation. The run stops; nothing is written."""


# ------------------------------------------------------------------ extract
def extract(conn: sqlite3.Connection) -> pd.DataFrame:
    claims = pd.read_sql("SELECT * FROM claim", conn)
    providers = pd.read_sql("SELECT npi, provider_name, state_code FROM provider", conn)
    statuses = pd.read_sql("SELECT status_code, is_payable FROM claim_status", conn)
    log.info("Extracted %d claims, %d providers, %d status codes",
             len(claims), len(providers), len(statuses))

    missing = [c for c in REQUIRED_CLAIM_COLUMNS if c not in claims.columns]
    if missing:
        raise PipelineError(f"claim table is missing columns: {missing}")

    df = claims.merge(providers, on="npi", how="left", validate="many_to_one")
    df = df.merge(statuses, on="status_code", how="left", validate="many_to_one")
    return df


# ------------------------------------------------------------------ validate
def validate(df: pd.DataFrame) -> None:
    problems = []
    if df["claim_id"].duplicated().any():
        problems.append("duplicate claim_id values")
    if df["provider_name"].isna().any():
        problems.append(f"claims with unknown npi: {df.loc[df.provider_name.isna(), 'claim_id'].tolist()}")
    if df["is_payable"].isna().any():
        problems.append(f"claims with unknown status_code: {df.loc[df.is_payable.isna(), 'claim_id'].tolist()}")
    for col in AMOUNT_COLUMNS:
        if (df[col] < 0).any():
            problems.append(f"negative values in {col}")
    if (df["service_through_date"] < df["service_from_date"]).any():
        problems.append("service_through_date earlier than service_from_date")
    if problems:
        raise PipelineError("Input validation failed: " + "; ".join(problems))
    log.info("Validation passed for %d claims", len(df))


# ------------------------------------------------------------------ transform
def enrich(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rules = cfg["rules"]
    out = df.copy()
    for c in ("service_from_date", "service_through_date", "received_date"):
        out[c] = pd.to_datetime(out[c], format="%Y-%m-%d")

    key = out["facility_type_code"].astype(str) + "-" + out["bill_classification_code"].astype(str)
    out["claim_category"] = key.map(cfg["claim_category_map"]).fillna(cfg["default_claim_category"])

    dec = rules["amount_decimals"]
    out["patient_responsibility"] = (out["deductible_amount"] + out["coinsurance_amount"]).round(dec)
    out["provider_paid_amount"] = (out["allowed_amount"] - out["patient_responsibility"]).round(dec)

    out["days_to_receive"] = (out["received_date"] - out["service_through_date"]).dt.days.astype("Int64")
    out["timely_filing_flag"] = pd.Series(pd.NA, index=out.index, dtype="object")
    has_date = out["days_to_receive"].notna()
    late = has_date & (out["days_to_receive"] > rules["timely_filing_days"])
    out.loc[has_date, "timely_filing_flag"] = "ON_TIME"
    out.loc[late, "timely_filing_flag"] = "LATE"

    out["report_month"] = out["service_from_date"].dt.strftime("%Y-%m")
    return out


def assign_exception_reason(df: pd.DataFrame, cfg: dict) -> pd.Series:
    checks = {
        "MISSING_RECEIVED_DATE": df["received_date"].isna(),
        "NOT_PAYABLE": df["is_payable"] != "Y",
        "LATE_FILING": df["timely_filing_flag"] == "LATE",
    }
    reason = pd.Series(pd.NA, index=df.index, dtype="object")
    for name in reversed(cfg["exception_priority"]):   # highest priority applied last
        reason[checks[name]] = name
    return reason


def build_outputs(df: pd.DataFrame, cfg: dict, run_ts: str):
    rules = cfg["rules"]
    df = df.copy()
    df["exception_reason"] = assign_exception_reason(df, cfg)
    included = df[df["exception_reason"].isna()]
    excluded = df[df["exception_reason"].notna()]

    date_fmt = lambda s: s.dt.strftime("%Y-%m-%d")

    detail = included.assign(
        service_from_date=date_fmt(included["service_from_date"]),
        service_through_date=date_fmt(included["service_through_date"]),
        received_date=date_fmt(included["received_date"]),
    )[[
        "claim_id", "npi", "beneficiary_id", "report_month", "claim_category",
        "service_from_date", "service_through_date", "received_date",
        "billed_amount", "allowed_amount", "deductible_amount", "coinsurance_amount",
        "patient_responsibility", "provider_paid_amount", "days_to_receive", "timely_filing_flag",
    ]].sort_values("claim_id").reset_index(drop=True)

    keys = ["npi", "provider_name", "state_code", "report_month", "claim_category"]
    summary = (included.groupby(keys, as_index=False)
               .agg(claim_count=("claim_id", "count"),
                    total_billed_amount=("billed_amount", "sum"),
                    total_allowed_amount=("allowed_amount", "sum"),
                    total_patient_responsibility=("patient_responsibility", "sum"),
                    total_provider_paid_amount=("provider_paid_amount", "sum"),
                    avg_days_to_receive=("days_to_receive", "mean")))
    for c in ["total_billed_amount", "total_allowed_amount",
              "total_patient_responsibility", "total_provider_paid_amount"]:
        summary[c] = summary[c].round(rules["amount_decimals"])
    summary["payment_rate"] = (summary["total_provider_paid_amount"] /
                               summary["total_billed_amount"]).round(rules["rate_decimals"])
    summary["avg_days_to_receive"] = summary["avg_days_to_receive"].astype(float).round(rules["avg_days_decimals"])
    summary = summary[keys + [
        "claim_count", "total_billed_amount", "total_allowed_amount", "total_patient_responsibility",
        "total_provider_paid_amount", "payment_rate", "avg_days_to_receive",
    ]].sort_values(["npi", "report_month", "claim_category"]).reset_index(drop=True)

    exceptions = excluded.assign(run_timestamp=run_ts)[[
        "claim_id", "npi", "status_code", "days_to_receive", "timely_filing_flag",
        "exception_reason", "run_timestamp",
    ]].sort_values("claim_id").reset_index(drop=True)

    # reconciliation: every input claim is accounted for exactly once
    if len(detail) + len(exceptions) != len(df):
        raise PipelineError("Reconciliation failed: included + exceptions != input claims")
    if summary["claim_count"].sum() != len(detail):
        raise PipelineError("Reconciliation failed: summary claim_count != claim_detail rows")
    log.info("Included %d claims, excluded %d (%s)", len(detail), len(exceptions),
             exceptions["exception_reason"].value_counts().to_dict())
    log.info("Summary rows: %d", len(summary))
    return detail, summary, exceptions


# ------------------------------------------------------------------ load
def write_outputs(outputs: dict, output_db: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output_db) as conn:
        for name, frame in outputs.items():
            frame.to_sql(name, conn, if_exists="replace", index=False)
            frame.to_csv(output_dir / f"{name}.csv", index=False)
            log.info("Wrote %s: %d rows", name, len(frame))


def run(config_path: Path) -> dict:
    base = config_path.resolve().parent
    cfg = yaml.safe_load(config_path.read_text())
    source_db = (base / cfg["source_db"]).resolve()
    if not source_db.exists():
        raise PipelineError(f"source database not found: {source_db}")

    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log.info("Run started %s, source=%s", run_ts, source_db)
    with sqlite3.connect(source_db) as conn:
        raw = extract(conn)
    validate(raw)
    detail, summary, exceptions = build_outputs(enrich(raw, cfg), cfg, run_ts)
    outputs = {"claim_detail": detail, "provider_monthly_summary": summary,
               "claim_exceptions": exceptions}
    write_outputs(outputs, base / cfg["output_db"], base / cfg["output_dir"])
    log.info("Run completed")
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    try:
        run(Path(args.config))
    except PipelineError as exc:
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
