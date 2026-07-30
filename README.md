# ECO Pulse CA

An open, station-level air quality benchmark for Central Asia — Uzbekistan, Kazakhstan,
Kyrgyzstan, Tajikistan, Turkmenistan — with **pre-registered** spatial (leave-city-out) and
blocked-temporal splits.

The point of this repository is not a model. It is the artifact that makes models in this
region *comparable*: frozen splits, a documented QC pipeline, and a baseline ladder that
future work has to beat honestly.

> **Status:** Phase 0 (literature review) complete. Phase 1 (ground truth) in progress.
> See [`STATUS.md`](STATUS.md) for the live picture and [`PAPER_CLAIM.md`](PAPER_CLAIM.md)
> for what this work does and does not claim.

---

## Quickstart

```bash
python scripts/setup_env.py
```

That creates the pinned Python 3.12 environment in `.venv` and installs the project. It
works with or without [`uv`](https://docs.astral.sh/uv/): if `uv` is on PATH it is used
(and can download a 3.12 for you), otherwise the script finds a suitable interpreter and
falls back to `venv` + `pip`. It **executes** each candidate interpreter rather than
trusting version metadata — on our own Windows machine the `py` launcher advertised a 3.12
that would not start. Re-running is safe: a healthy `.venv` is reused, not rebuilt. Pass
`--force` to recreate it.

Equivalent, once the environment exists: `make setup` or `python tasks.py setup`.

<details>
<summary><b>Windows: if <code>python tasks.py …</code> fails with exit 103</b></summary>

The Microsoft Store build of Python runs in a sandbox that cannot see
`%APPDATA%\Roaming`. If your 3.12 lives there (which is where `uv` installs it), any
subprocess into `.venv` dies with `No Python at '…'`. The environment is fine; the
launcher cannot reach it. `tasks.py` detects this and prints the fix. The quickest one:

```bash
.venv\Scripts\python.exe tasks.py test
```
</details>

Run the full test suite — **no credentials required**, everything runs against committed
fixtures:

```bash
python -m pytest
```

## What a reviewer can do, and what needs a key

Be precise about this, because "one command reproduces everything" is only true once the
ground-truth panel exists locally.

**Without any credentials, from a clean clone:**

| Goal | Command |
|---|---|
| Verify the frozen benchmark | `cd benchmark/splits && sha256sum -c splits.sha256` |
| Run the full test suite (538 tests, offline fixtures) | `python tasks.py test` |
| Lint and type-check | `python tasks.py lint && python tasks.py typecheck` |
| Rebuild every table and re-render the manuscript | `python tasks.py paper` |

The splits **are** the benchmark and they are committed, so verifying them requires no
rebuild and no key.

**To regenerate the numbers from source**, the derived ground-truth panel must be built
first. It is not committed — `data/MANIFEST.md` records its provenance, and the per-station
OpenAQ licence terms are not yet transcribed, so the archive is not redistributed here.
With an `OPENAQ_API_KEY` in `.env` (see [`REGISTRATION.md`](REGISTRATION.md)):

```bash
python -m ecopulse_ca.ingest.openaq --census
python scripts/pull_panel.py
```

Then the single command that rebuilds every reported number end to end:

```bash
make reproduce
```

Equivalently, where `make` is absent: `python tasks.py reproduce`. It runs lint →
typecheck → tests → splits (frozen and hash-verified *before* any model sees data) →
baselines (5 seeds) → tables → manuscript render → stitch, and stops at the first failure.
Attempting it without the panel fails with instructions rather than a bare traceback.

`make reproduce` is idempotent: re-running it leaves the working tree clean, including
`splits.sha256`, whose freeze timestamp is preserved when the hash is unchanged.

On Windows, where `make` is absent, `python tasks.py <target>` runs every Makefile target.
The Makefile delegates to `tasks.py`, so the two cannot issue different commands, and tests
assert the delegation holds.

---

## The rules this repo enforces mechanically

These are the failure modes that make air quality ML results untrustworthy. Each is a test,
not a convention, because conventions do not fail the build.

| Rule | Enforced by |
|---|---|
| **No random splits, ever** | `tests/test_no_random_splits.py` — a static scan of `src/`. Air quality data is autocorrelated in space and time; a shuffle puts the same station and often the same hour on both sides of the split. |
| **Splits are immutable once frozen** | `benchmark/splits/splits.sha256`, hash-checked. Poor predictor coverage in a frozen city is *reported*, never fixed by re-freezing. |
| **No target leakage** | Same-timestamp co-located PM2.5 is barred; every feature's provenance is traced. |
| **No lookahead in operational features** | ERA5/CAMS reanalysis do not exist at prediction time. Results using them are labelled reanalysis-oracle ablations, never deployed numbers. |
| **Nothing dropped silently** | Every QC rule reports its **n-effect** into [`data/DECISIONS.md`](data/DECISIONS.md). |
| **Timezones validated against physics** | Diurnal-shape cross-correlation, not metadata — including detection of offsets that change mid-record. |
| **Every number is traceable** | `run_id` + git SHA + config hash in the run log. |

## Two tasks, never mixed in one table

- **Task F — forecasting.** At a monitored station, predict PM2.5 at t+24/48/72 h.
  Ladder: persistence → diurnal persistence → climatology → ridge → LightGBM.
- **Task N — nowcasting.** Estimate PM2.5 in a held-out city with **zero** local labels.
  Ladder: nearest-monitor → IDW → ordinary kriging → (later) satellite models.

Task N's interpolation rungs are the comparison reviewers actually use against satellite
models — *does it beat interpolating from nearby monitors?* — and they are routinely
omitted. They are built first here.

---

## Layout

```
research/        LITERATURE.md, GAP.md          — Phase 0, with per-source verification depth
data/            MANIFEST.md, DECISIONS.md      — provenance and every filtering decision
benchmark/       splits/ (committed + hashed)   — the deliverable
src/ecopulse_ca/ ingest/ qc/ splits/ tasks/ models/ eval/ registry/
tests/           the rules above, as tests
paper/           figures and tables, generated by script only
```

## Regional context that shapes the design

From the OpenAQ 2024 data landscape report and the Phase 0 review — all of it load-bearing,
not background:

- **Turkmenistan has no national air quality monitoring at all.** Ashgabat enters only via
  the US Embassy monitor.
- **Kazakhstan shares its data only with people inside Kazakhstan.** A benchmark a third
  party cannot reconstruct is not open, so Kazakh stations enter only through an
  independently retrievable path.
- **Only Kyrgyzstan shares fully openly**; Tajikistan began sharing in 2024.
- The **US Embassy network is the benchmark's spine** — the only consistent multi-country
  reference in the region.
- **MAIAC AOD missingness correlates with the target**: retrievals fail during dust storms,
  snow and heavy cloud, i.e. the extreme episodes. Missing-AOD rows are modelled, never
  dropped — dropping them conditions on "retrieval succeeded" and biases results toward
  calm, clear, low-concentration days.

## Licence

MIT for the code. Data licences are recorded per source in [`data/MANIFEST.md`](data/MANIFEST.md).
