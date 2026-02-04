# QA Verification (Manual)

This directory contains a small, repeatable manual QA set for validating:
- query routing
- evidence mix (paper vs code)
- explicit missing-evidence behavior

Files:
- `tests/qa/qa_set.json` (source of truth)
- `tests/qa/qa_runner.py` (no external deps)

Run (after starting backend locally):

```bash
python tests/qa/qa_runner.py --project-id <PROJECT_ID> --in tests/qa/qa_set.json --out tests/qa/runs/latest.json
```

Review fields in the output JSON:
- `route`
- `evidence_mix`
- `insufficient_evidence`
- `answer`
