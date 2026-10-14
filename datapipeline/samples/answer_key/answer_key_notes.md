# Answer Key Notes (do not share with the agent)

Use this to score the agent at each step of the demo.

## Dataset facts
- 120 claims, 12 providers, 5 status codes (P, A, R, V, D). All synthetic.
- Legacy job includes **97** claims; the new pipeline includes **87** and sends **33** to exceptions (27 NOT_PAYABLE, 4 LATE_FILING, 2 MISSING_RECEIVED_DATE).
- Regenerate everything with `python generate_data.py` (fixed seed, same output every time).

## Step 1–2: rules the agent should extract from the legacy SQL
| # | Rule | Legacy location |
|---|---|---|
| L1 | Exclude status R (rejected) and V (voided) | STEP 1 WHERE clause |
| L2 | Category from first 2 bill type digits: 11 = IP, 13 = OP, else OT | STEP 1 CASE |
| L3 | Net paid = allowed − patient responsibility | STEP 1 NET_PD_AMT |
| L4 | Report month = YYYYMM of service FROM date | STEP 1 RPT_MTH |
| L5 | Timely filing: drop if received − service FROM date > 365 | STEP 1 RCV_LAG_DYS + STEP 3 |
| L6 | Aggregate count, charges, allowed, net paid by provider / month / category | STEP 4 |
| L7 | Only claims with a matching provider are reported (INNER JOIN) | STEP 1 join |

## Planted issues the agent should flag (not silently fix or copy)
| # | Issue | What a good agent says |
|---|---|---|
| P1 | Status D (Denied) exists in STS but is not excluded; the hardcoded list only has R and V | Ambiguity: were denials meant to be counted? 11 denied claims are in the legacy report with $0 allowed, inflating claim counts |
| P2 | Claims with a null RCVD_DT survive the timely filing DELETE because `NULL > 365` is not true | Legacy defect: 2 claims (C25000027, C25000096) are reported with no received date |
| P3 | `TMP_ADJ_FLG` is calculated but never used | Dead column; not carried forward |
| P4 | STEP 2 hospice split is commented out ("do not re-enable") | Dead code; hospice stays in Other; confirm with SME |
| P5 | INNER JOIN silently drops claims whose NPI is missing from PROV (none in this dataset) | New spec fails the run instead; note as behavior change |

## Expected behavior-change log
| Change | Cause | Claims affected |
|---|---|---|
| Denied claims excluded (via is_payable) | Spec change / resolves P1 | C25000008, 013, 026, 032, 057, 058, 064, 084, 093, 094, 106 |
| Missing received date → exception | Spec change / fixes P2 | C25000027, C25000096 |
| Timely filing measured from THROUGH date, not FROM date | Spec change | Now included: C25000010 (359 days), C25000034 (360), C25000072 (355); legacy dropped them |
| Excluded claims written to claim_exceptions instead of dropped | Spec change | All 33 exceptions |
| Unknown NPI fails the run instead of being dropped | Spec change / P5 | None in this dataset |
| Category labels IP/OP/OT → Inpatient/Outpatient/Other; month YYYYMM → YYYY-MM | Spec change | All rows |

## Totals (for a quick sanity check)
| | Legacy | New |
|---|---|---|
| Claims in report | 97 | 87 |
| Total billed | 935,050.56 | 840,903.54 |
| Total provider paid | 407,898.44 | 418,445.80 |

## Edge cases built into the data
- 365 days exactly (C25000045) → ON_TIME; 366 days (C25000089) → LATE
- Both not payable and late (C25000102, status R, 420 days) → reason NOT_PAYABLE (priority test)

## Scoring the generated pipeline
    python compare_outputs.py <folder with the agent's three CSVs>
PASS on all three tables = functionally equivalent to the reference. The agent's code does not need to look like reference_pipeline.py.
