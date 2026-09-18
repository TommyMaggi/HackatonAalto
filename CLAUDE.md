# Trustworthy Process Monitor

Read `CONTRACTS.md` first and treat it as binding. It is the shared contract for
the whole team; this file adds only what is specific to working here with Claude
Code.

## The four rules that fail CI

1. Raw data never leaves. All model calls go through `call_model()` in
   `trust/gateway.py`. No LLM SDK import outside `trust/`.
2. No original column names after S1. Only `col_NNN`. The strings `xmeas` and
   `xmv` are banned outside `pipeline/s1_ingest.py` and `eval/`.
3. `faultNumber` and `fault_status` are banned under `pipeline/`. They live in
   `eval/`.
4. No chemistry vocabulary in prompt literals. Prompts are generated from
   `artifacts/profiles.json` by a function.

Before you finish any task, run `make check`. If it fails, you are not done.

## Architecture

Seven stages communicating only through JSON artifacts in `artifacts/`.
No stage imports another stage. Schemas in `contracts/`. See `CONTRACTS.md` §1.

## Evidence

Every inference carries `evidence_ids` pointing at objects that conform to
`contracts/evidence.schema.json`. A claim you cannot attach evidence to is
written with `epistemic_status: "assumed"` and low confidence, or not written.

Stated low confidence beats unsupported certainty. This is a scoring criterion,
not a style note.

## Stack

DuckDB over Parquet for anything touching the dataset. Never pandas on the
6 GB CSV. Develop against `artifacts/examples/`, not the full file.

## Working here

- Plan before implementing any module larger than one file.
- One stage per session. Do not build two stages in one conversation.
- Start from the JSON schema in `contracts/`, not from prose.
- Touch only files your role owns (`CONTRACTS.md` §6).
