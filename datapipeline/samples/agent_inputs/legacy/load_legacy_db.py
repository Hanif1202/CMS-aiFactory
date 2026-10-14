"""
load_legacy_db.py
Loads legacy_data.xlsx (sheets PROV, CLM, STS) into legacy.db (SQLite),
reproducing the legacy table layout. Dates are stored as TEXT in YYYYMMDD form,
exactly as the legacy system holds them.

Usage:  python load_legacy_db.py
"""
import sqlite3
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
XLSX, DB = HERE / "legacy_data.xlsx", HERE / "legacy.db"

DDL = """
DROP TABLE IF EXISTS PROV;
CREATE TABLE PROV (
    PROV_NPI     CHAR(10)     NOT NULL PRIMARY KEY,
    PROV_NM      VARCHAR(60)  NOT NULL,
    PROV_ST      CHAR(2)
);
DROP TABLE IF EXISTS STS;
CREATE TABLE STS (
    STS_CD       CHAR(1)      NOT NULL PRIMARY KEY,
    STS_DESC     VARCHAR(20)
);
DROP TABLE IF EXISTS CLM;
CREATE TABLE CLM (
    CLM_ID       CHAR(9)      NOT NULL PRIMARY KEY,
    PROV_NPI     CHAR(10)     NOT NULL,
    BENE_ID      CHAR(11)     NOT NULL,
    BILL_TYP     CHAR(3)      NOT NULL,
    SVC_FROM_DT  CHAR(8)      NOT NULL,
    SVC_THRU_DT  CHAR(8)      NOT NULL,
    RCVD_DT      CHAR(8),
    CLM_CHRG_AMT DECIMAL(11,2),
    CLM_ALWD_AMT DECIMAL(11,2),
    PT_RESP_AMT  DECIMAL(11,2),
    CLM_STS_CD   CHAR(1)
);
"""

TEXT_COLS = ["PROV_NPI", "PROV_NM", "PROV_ST", "STS_CD", "STS_DESC", "CLM_ID", "BENE_ID",
             "BILL_TYP", "SVC_FROM_DT", "SVC_THRU_DT", "RCVD_DT", "CLM_STS_CD"]

def main():
    sheets = pd.read_excel(XLSX, sheet_name=None, dtype={c: str for c in TEXT_COLS})
    with sqlite3.connect(DB) as conn:
        conn.executescript(DDL)
        for table in ("PROV", "STS", "CLM"):
            df = sheets[table].astype(object).where(sheets[table].notna(), None)
            conn.executemany(
                f"INSERT INTO {table} ({','.join(df.columns)}) VALUES ({','.join('?' * len(df.columns))})",
                df.itertuples(index=False, name=None))
            print(f"Loaded {table}: {len(df)} rows")

if __name__ == "__main__":
    main()
