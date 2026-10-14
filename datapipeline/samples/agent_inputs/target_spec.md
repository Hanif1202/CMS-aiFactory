# Target Specification: Provider Monthly Claim Summary

**Replaces:** legacy job `PRVSUM01` (`legacy/legacy_pipeline.sql`)
**Version:** 1.0 (mock specification for demonstration; all data is synthetic)

## 1. Purpose

Rebuild the legacy provider monthly claim summary so it runs on the new claims system's data model. The new pipeline produces a claim-level detail table, a provider summary report and an exceptions table, following the standards in section 7.

The legacy job remains the reference for *current* behavior. Where this specification defines a rule differently from the legacy job, **this specification wins**, and every such difference must be listed in the behavior-change log (section 8).

## 2. Target technology

| Item | Standard |
|---|---|
| Language | Python 3.11+ |
| Libraries | pandas, PyYAML (no other runtime dependencies) |
| Source database | SQLite: `new_system/new.db` |
| Output | Same three tables written to an output SQLite database **and** as CSV files, one per table, named `<table_name>.csv` |
| Configuration | YAML file; no business thresholds hardcoded in code |
| Tests | pytest |
| Deployment | Must run fully locally with no network access |

## 3. Source data model (new system)

### 3.1 `provider`
| Column | Type | Notes |
|---|---|---|
| npi | TEXT, PK | 10-digit National Provider Identifier |
| provider_name | TEXT | |
| state_code | TEXT | 2-letter state |

### 3.2 `claim`
| Column | Type | Notes |
|---|---|---|
| claim_id | TEXT, PK | |
| npi | TEXT, FK → provider | |
| beneficiary_id | TEXT | Synthetic MBI format |
| facility_type_code | TEXT | Type of bill, digit 1 (X12 837I CLM05-1) |
| bill_classification_code | TEXT | Type of bill, digit 2 |
| claim_frequency_code | TEXT | Type of bill, digit 3 (CLM05-3) |
| service_from_date | DATE (ISO text) | |
| service_through_date | DATE (ISO text) | |
| received_date | DATE (ISO text), nullable | |
| billed_amount | NUMERIC(11,2) | Total charges |
| allowed_amount | NUMERIC(11,2) | |
| deductible_amount | NUMERIC(11,2) | Beneficiary deductible applied |
| coinsurance_amount | NUMERIC(11,2) | Beneficiary coinsurance applied |
| status_code | TEXT, FK → claim_status | |

### 3.3 `claim_status`
| Column | Type | Notes |
|---|---|---|
| status_code | TEXT, PK | |
| status_description | TEXT | |
| is_payable | TEXT ('Y'/'N') | Controls inclusion. Status code lists must not be hardcoded. |

### 3.4 Field mapping from legacy

| Legacy (table.column) | New (table.column) | Change |
|---|---|---|
| PROV.PROV_NPI | provider.npi | Rename |
| PROV.PROV_NM | provider.provider_name | Rename; mixed case instead of upper case |
| PROV.PROV_ST | provider.state_code | Rename |
| CLM.CLM_ID | claim.claim_id | Rename |
| CLM.BENE_ID | claim.beneficiary_id | Rename |
| CLM.BILL_TYP | facility_type_code, bill_classification_code, claim_frequency_code | One 3-character code split into three fields |
| CLM.SVC_FROM_DT | claim.service_from_date | Text YYYYMMDD → DATE |
| CLM.SVC_THRU_DT | claim.service_through_date | Text YYYYMMDD → DATE |
| CLM.RCVD_DT | claim.received_date | Text YYYYMMDD → DATE |
| CLM.CLM_CHRG_AMT | claim.billed_amount | Rename |
| CLM.CLM_ALWD_AMT | claim.allowed_amount | Rename |
| CLM.PT_RESP_AMT | deductible_amount + coinsurance_amount | One amount split into two components |
| CLM.CLM_STS_CD | claim.status_code | Rename |
| STS (table) | claim_status (table) | Adds is_payable flag |

## 4. Calculated columns (claim level)

| Column | Rule |
|---|---|
| claim_category | `Inpatient` when facility_type_code = '1' and bill_classification_code = '1'; `Outpatient` when facility_type_code = '1' and bill_classification_code = '3'; otherwise `Other`. |
| patient_responsibility | deductible_amount + coinsurance_amount |
| provider_paid_amount | allowed_amount − patient_responsibility |
| days_to_receive | received_date − service_through_date, in whole days. Null when received_date is null. |
| timely_filing_flag | `LATE` when days_to_receive > timely filing limit (config, default 365); `ON_TIME` otherwise; null when days_to_receive is null. |
| report_month | Month of service_from_date, formatted `YYYY-MM`. |

## 5. Inclusion and exceptions

A claim is **included** in the report only if it has a received date, its status is payable (`is_payable = 'Y'`), and it is not late.

Every other claim is written to `claim_exceptions` with **exactly one** reason. When more than one applies, use the first in this priority order:

1. `MISSING_RECEIVED_DATE`: received_date is null
2. `NOT_PAYABLE`: claim_status.is_payable is not 'Y'
3. `LATE_FILING`: timely_filing_flag = 'LATE'

No claim may be dropped silently: included + exceptions must equal the input claim count.

## 6. Output tables

### 6.1 `claim_detail` (one row per included claim, sorted by claim_id)
claim_id, npi, beneficiary_id, report_month, claim_category, service_from_date, service_through_date, received_date, billed_amount, allowed_amount, deductible_amount, coinsurance_amount, patient_responsibility, provider_paid_amount, days_to_receive, timely_filing_flag

### 6.2 `provider_monthly_summary` (sorted by npi, report_month, claim_category)
Grouped by npi, provider_name, state_code, report_month and claim_category.

| Column | Rule |
|---|---|
| npi, provider_name, state_code, report_month, claim_category | Group keys |
| claim_count | Number of included claims |
| total_billed_amount | Sum of billed_amount |
| total_allowed_amount | Sum of allowed_amount |
| total_patient_responsibility | Sum of patient_responsibility |
| total_provider_paid_amount | Sum of provider_paid_amount |
| payment_rate | total_provider_paid_amount ÷ total_billed_amount |
| avg_days_to_receive | Mean of days_to_receive |

### 6.3 `claim_exceptions` (one row per excluded claim, sorted by claim_id)
claim_id, npi, status_code, days_to_receive, timely_filing_flag, exception_reason, run_timestamp (UTC, ISO-8601)

### 6.4 Rounding
Amounts to 2 decimals, payment_rate to 4 decimals, avg_days_to_receive to 1 decimal. Dates in outputs as `YYYY-MM-DD`.

## 7. Engineering standards

- **Structure:** separate extract, validate, transform and load steps as functions; single entry point runnable from the command line with a `--config` argument.
- **Configuration:** source path, output paths, timely filing limit, rounding and category mapping come from the YAML config.
- **Validation (fail fast):** stop the run with a clear error, writing nothing, if required columns are missing, claim_id is duplicated, a claim references an unknown npi or status_code, any amount is negative, or service_through_date is earlier than service_from_date.
- **Logging:** Python `logging`; log row counts after extract, after validation, included vs excluded (by reason) and rows written per table.
- **Reconciliation:** assert included + exceptions = input claims, and sum of claim_count = claim_detail rows.
- **Tests:** unit tests for every calculated column, the 365/366-day boundary, exception priority, reconciliation and each validation rule.
- **Code style:** PEP 8, type hints on public functions, docstrings on modules and functions.

## 8. Required deliverables from the migration

1. Pipeline code, config file and pytest suite meeting sections 2–7.
2. **Rules inventory:** every business rule found in the legacy job, with the legacy line(s) it came from.
3. **Behavior-change log:** every case where the new pipeline behaves differently from the legacy job, with the reason (specification change, legacy defect or ambiguity).
4. **Open questions:** anything in the legacy code that is ambiguous or looks unintended, flagged for SME review rather than assumed.
5. Run evidence: test results and output row counts.
