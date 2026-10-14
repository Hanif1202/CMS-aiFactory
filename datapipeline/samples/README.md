# Data Pipeline Mock Sample: Provider Monthly Claim Summary

Mock legacy artifact for the Agentic AI Migration Factory demo. All data is synthetic (no PHI).

## Folders

**agent_inputs/**: everything the agent is given
- `legacy/legacy_data.xlsx`: legacy source data (sheets PROV, CLM, STS; 120 claims)
- `legacy/legacy.db`: the same data loaded into SQLite (`load_legacy_db.py` rebuilds it)
- `legacy/legacy_pipeline.sql`: legacy batch job PRVSUM01
- `legacy/run_legacy.sh`: nightly wrapper; runs the job and extracts the report
- `legacy/legacy_output_RPT_PROV_SUM.csv`: current legacy report output
- `new_system/new_data.xlsx` + `new.db`: the same claims in the new system's structure (`load_new_db.py` rebuilds it)
- `target_spec.md`: what the pipeline is being modernized into

**answer_key/**: keep away from the agent
- `reference_pipeline.py`, `config.yaml`, `test_reference.py`: reference implementation and tests
- `expected_output/`: the three expected output tables as CSV
- `compare_outputs.py`: scores the agent's output against expected
- `answer_key_notes.md`: rules to extract, planted issues, expected behavior changes, totals
- `generate_data.py`: regenerates both datasets (fixed seed)

## Run it

    pip install -r answer_key/requirements.txt

    # legacy job
    sh agent_inputs/legacy/run_legacy.sh

    # reference pipeline and tests
    cd answer_key
    python reference_pipeline.py
    python -m pytest -q

    # score the agent's output
    python compare_outputs.py path/to/agent_output_folder

## Tech stack
Legacy: SQLite, DB2/Teradata-style SQL, shell wrapper. Target: Python 3.11, pandas, PyYAML, pytest, SQLite. Runs fully offline.
