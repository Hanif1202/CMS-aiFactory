"""
load_new_db.py
Loads new_data.xlsx (sheets provider, claim, claim_status) into new.db (SQLite),
following the new-system schema in target_spec.md. SQLite has no native DATE type,
so dates are stored as ISO-8601 TEXT (YYYY-MM-DD).

Usage:  python load_new_db.py
"""
import sqlite3
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
XLSX, DB = HERE / "new_data.xlsx", HERE / "new.db"

DDL = """
DROP TABLE IF EXISTS provider;
CREATE TABLE provider (
    npi                       TEXT NOT NULL PRIMARY KEY,
    provider_name             TEXT NOT NULL,
    state_code                TEXT
);
DROP TABLE IF EXISTS claim_status;
CREATE TABLE claim_status (
    status_code               TEXT NOT NULL PRIMARY KEY,
    status_description        TEXT NOT NULL,
    is_payable                TEXT NOT NULL CHECK (is_payable IN ('Y','N'))
);
DROP TABLE IF EXISTS claim;
CREATE TABLE claim (
    claim_id                  TEXT NOT NULL PRIMARY KEY,
    npi                       TEXT NOT NULL REFERENCES provider(npi),
    beneficiary_id            TEXT NOT NULL,
    facility_type_code        TEXT NOT NULL,
    bill_classification_code  TEXT NOT NULL,
    claim_frequency_code      TEXT NOT NULL,
    service_from_date         DATE NOT NULL,
    service_through_date      DATE NOT NULL,
    received_date             DATE,
    billed_amount             NUMERIC(11,2) NOT NULL,
    allowed_amount            NUMERIC(11,2) NOT NULL,
    deductible_amount         NUMERIC(11,2) NOT NULL,
    coinsurance_amount        NUMERIC(11,2) NOT NULL,
    status_code               TEXT NOT NULL REFERENCES claim_status(status_code)
);
"""

TEXT_COLS = ["npi", "provider_name", "state_code", "status_code", "status_description",
             "is_payable", "claim_id", "beneficiary_id", "facility_type_code",
             "bill_classification_code", "claim_frequency_code"]
DATE_COLS = ["service_from_date", "service_through_date", "received_date"]

def main():
    sheets = pd.read_excel(XLSX, sheet_name=None, dtype={c: str for c in TEXT_COLS})
    for c in DATE_COLS:
        sheets["claim"][c] = pd.to_datetime(sheets["claim"][c]).dt.strftime("%Y-%m-%d")
    with sqlite3.connect(DB) as conn:
        conn.executescript(DDL)
        for table in ("provider", "claim_status", "claim"):
            df = sheets[table].astype(object).where(sheets[table].notna(), None)
            conn.executemany(
                f"INSERT INTO {table} ({','.join(df.columns)}) VALUES ({','.join('?' * len(df.columns))})",
                df.itertuples(index=False, name=None))
            print(f"Loaded {table}: {len(df)} rows")

if __name__ == "__main__":
    main()
