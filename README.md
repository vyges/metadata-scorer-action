# Vyges Metadata Scorer Action

Score a `vyges-metadata.json` against the Vyges integration-readiness rubric
(0–100) and optionally fail CI when below a threshold. Runs as a CI status
check inside every IP repo so missing fields are surfaced at PR time.

## Usage

Add to `.github/workflows/metadata-score.yml` in any IP repo:

```yaml
name: Metadata score
on:
  push: { branches: [main] }
  pull_request: {}

jobs:
  score:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: vyges/metadata-scorer-action@v1
        with:
          file: vyges-metadata.json
          threshold: 80   # fail PR when score drops below this
```

## Inputs

| Name | Default | Description |
|---|---|---|
| `file` | `vyges-metadata.json` | Path to the metadata file |
| `threshold` | `0` | Fail action when score < threshold. `0` = advisory only |
| `summary` | `true` | Write a job summary panel with the score table |

## Outputs

| Name | Example | Description |
|---|---|---|
| `score` | `93` | Total score, 0–100 |
| `tier` | `Good` | `Good` ≥80, `Medium` 60–79, `High-risk` <60 |
| `breakdown` | `{"identity":20,"interfaces":23,...}` | Per-dimension JSON |
| `gaps` | `["interfaces: bus.signals", ...]` | Missing fields, JSON array |

## Scoring rubric (100 pts)

| Dimension | Max | What it checks |
|---|---:|---|
| Identity | 20 | name, version, license, description, maturity |
| Interfaces | 25 | clock + reset declared; bus interface with protocol + signals |
| Parameters | 10 | parameters[] declared with descriptions |
| Implementation | 20 | target[], design_type[], asic{} or fpga{} |
| Verification | 15 | test{} block with coverage and testbenches |
| Provenance | 10 | source.url, maintainers[], created/updated |

Tiers: ≥80 Good, 60–79 Medium, <60 High-risk.

## Reading the job summary

After every run, the **Summary** tab on the workflow run shows a
per-dimension table and a list of any gaps:

> ## Vyges metadata score: **80/100** (Good)
>
> | Dimension | Score | Max |
> |---|---:|---:|
> | identity | 20 | 20 |
> | interfaces | 13 | 25 |
> | … | … | … |
>
> ### Gaps
> - `interfaces: interfaces[].bus.signals`
> - `verification: test.testbenches`

## Local use

```sh
git clone https://github.com/vyges/metadata-scorer-action
cd metadata-scorer-action
VYGES_SCORER_FILE=path/to/vyges-metadata.json python scorer_action.py
```

## License

© 2026 Vyges/TrustStix Inc.
Licensed under the Apache License, Version 2.0 — see [`LICENSE`](LICENSE)
and [`NOTICE`](NOTICE).

The scorer module (`scorer.py`) is the canonical Vyges integration-readiness
rubric.

Bug reports, rubric proposals, commercial inquiries, or anything else:
please use **https://vyges.com/contact** — that form routes to the GitHub
Issues page we track.
