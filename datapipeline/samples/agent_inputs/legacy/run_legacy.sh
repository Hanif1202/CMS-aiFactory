#!/bin/sh
# ---------------------------------------------------------------------
#  RUN_LEGACY.SH  -  NIGHTLY WRAPPER FOR JOB PRVSUM01
#  RUNS legacy_pipeline.sql AGAINST legacy.db AND EXTRACTS RPT_PROV_SUM
#  TO legacy_output_RPT_PROV_SUM.csv
# ---------------------------------------------------------------------
cd "$(dirname "$0")" || exit 8
DB=legacy.db
SQL=legacy_pipeline.sql
OUT=legacy_output_RPT_PROV_SUM.csv

echo "$(date '+%Y-%m-%d %H:%M:%S') PRVSUM01 START"

if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB" < "$SQL" || { echo "PRVSUM01 ABEND RC=8"; exit 8; }
    sqlite3 -header -csv "$DB" "SELECT * FROM RPT_PROV_SUM;" > "$OUT"
else
    python3 - "$DB" "$SQL" "$OUT" << 'PY' || { echo "PRVSUM01 ABEND RC=8"; exit 8; }
import csv, sqlite3, sys
db, sql, out = sys.argv[1:4]
con = sqlite3.connect(db)
con.executescript(open(sql).read())
con.commit()
cur = con.execute("SELECT * FROM RPT_PROV_SUM")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([d[0] for d in cur.description])
    w.writerows(cur.fetchall())
PY
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') PRVSUM01 END RC=0  OUTPUT=$OUT"
