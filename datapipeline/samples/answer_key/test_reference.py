"""
test_reference.py  (ANSWER KEY)
pytest tests for reference_pipeline.py. Run:  python -m pytest -q
"""
from pathlib import Path

import pandas as pd
import pytest
import yaml

import reference_pipeline as rp

CFG = yaml.safe_load(Path(__file__).with_name("config.yaml").read_text())


def make_claim(**overrides):
    row = dict(
        claim_id="T001", npi="1000000001", beneficiary_id="1AA0AA0AA00",
        facility_type_code="1", bill_classification_code="1", claim_frequency_code="1",
        service_from_date="2025-03-01", service_through_date="2025-03-05",
        received_date="2025-03-20", billed_amount=10000.00, allowed_amount=6000.00,
        deductible_amount=1676.00, coinsurance_amount=0.00, status_code="P",
        provider_name="Test Hospital", state_code="NY", is_payable="Y",
    )
    row.update(overrides)
    return row


def frame(*rows):
    return pd.DataFrame(list(rows))


def run_rows(*rows):
    return rp.build_outputs(rp.enrich(frame(*rows), CFG), CFG, "2026-01-01T00:00:00Z")


# ---------------------------------------------------------------- calculated columns
@pytest.mark.parametrize("fac,cls,expected", [
    ("1", "1", "Inpatient"), ("1", "3", "Outpatient"),
    ("1", "2", "Other"), ("8", "1", "Other"),
])
def test_claim_category(fac, cls, expected):
    out = rp.enrich(frame(make_claim(facility_type_code=fac, bill_classification_code=cls)), CFG)
    assert out.loc[0, "claim_category"] == expected


def test_patient_responsibility_and_provider_paid():
    out = rp.enrich(frame(make_claim(allowed_amount=1000.00, deductible_amount=257.00,
                                     coinsurance_amount=148.60)), CFG)
    assert out.loc[0, "patient_responsibility"] == pytest.approx(405.60)
    assert out.loc[0, "provider_paid_amount"] == pytest.approx(594.40)


def test_days_to_receive_uses_through_date():
    out = rp.enrich(frame(make_claim(service_from_date="2025-01-01",
                                     service_through_date="2025-01-11",
                                     received_date="2026-01-06")), CFG)
    assert out.loc[0, "days_to_receive"] == 360          # 369 if the from date were used
    assert out.loc[0, "timely_filing_flag"] == "ON_TIME"


@pytest.mark.parametrize("days,flag", [(365, "ON_TIME"), (366, "LATE")])
def test_timely_filing_boundary(days, flag):
    thru = pd.Timestamp("2025-02-01")
    received = (thru + pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    out = rp.enrich(frame(make_claim(service_from_date="2025-02-01",
                                     service_through_date="2025-02-01",
                                     received_date=received)), CFG)
    assert out.loc[0, "timely_filing_flag"] == flag


# ---------------------------------------------------------------- exceptions
def test_exception_reasons_and_priority():
    detail, summary, exc = run_rows(
        make_claim(claim_id="OK"),
        make_claim(claim_id="NOPAY", status_code="D", is_payable="N"),
        make_claim(claim_id="LATE", received_date="2026-06-01"),
        make_claim(claim_id="NODATE", received_date=None),
        make_claim(claim_id="BOTH", status_code="R", is_payable="N", received_date="2026-06-01"),
    )
    reasons = dict(zip(exc.claim_id, exc.exception_reason))
    assert reasons == {"NOPAY": "NOT_PAYABLE", "LATE": "LATE_FILING",
                       "NODATE": "MISSING_RECEIVED_DATE", "BOTH": "NOT_PAYABLE"}
    assert detail.claim_id.tolist() == ["OK"]


def test_reconciliation_counts():
    detail, summary, exc = run_rows(make_claim(claim_id="A"), make_claim(claim_id="B"),
                                    make_claim(claim_id="C", status_code="V", is_payable="N"))
    assert len(detail) + len(exc) == 3
    assert summary.claim_count.sum() == len(detail)


# ---------------------------------------------------------------- summary
def test_summary_aggregation_and_payment_rate():
    detail, summary, _ = run_rows(
        make_claim(claim_id="A", billed_amount=1000.0, allowed_amount=600.0,
                   deductible_amount=0.0, coinsurance_amount=0.0, received_date="2025-03-15"),
        make_claim(claim_id="B", billed_amount=3000.0, allowed_amount=1400.0,
                   deductible_amount=100.0, coinsurance_amount=100.0, received_date="2025-03-25"),
    )
    row = summary.iloc[0]
    assert row.claim_count == 2
    assert row.total_billed_amount == pytest.approx(4000.0)
    assert row.total_provider_paid_amount == pytest.approx(1800.0)
    assert row.payment_rate == pytest.approx(0.45)
    assert row.avg_days_to_receive == pytest.approx(15.0)


# ---------------------------------------------------------------- validation
def test_validation_rejects_unknown_status():
    with pytest.raises(rp.PipelineError):
        rp.validate(frame(make_claim(is_payable=None)))


def test_validation_rejects_negative_amount():
    with pytest.raises(rp.PipelineError):
        rp.validate(frame(make_claim(allowed_amount=-5.0)))
