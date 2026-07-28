# Data Access Registration

Every predictor source in this project sits behind an account and a licence acceptance.
**Claude cannot create accounts or accept licences on your behalf** — both your project
rules and the assistant's operating rules prohibit it. This file lists exactly what to
register for, in priority order, and what each one unblocks.

Once you have a key, put it in `.env` (copy `.env.example`). `.env` is gitignored and must
never appear in a notebook, a commit, or a log line.

---

## Increment 1 — required now

### 1. OpenAQ v3 API key — **the only blocker for the current increment**

- Register: <https://explore.openaq.org/register> (free)
- The key arrives by email; it authenticates via an `X-API-Key` header.
- Put it in `.env` as `OPENAQ_API_KEY=...`
- **Unblocks:** all ground-truth ingestion, QC, split construction, and the entire
  credential-free baseline ladder — i.e. all of `benchmark v1.0.0`.

Until this exists, the ingestion client runs against committed offline fixtures so the
test suite still passes. No number derived from fixtures is ever reported as a result.

### 2. US Embassy / State Department monitors

Historical PM2.5 files for Tashkent, Astana, Almaty, Bishkek, and Dushanbe are published
as direct downloads and *may* not need a key. If a key turns out to be required, it is the
AirNow API key: <https://docs.airnowapi.org/account/request/>. To be confirmed during
Phase 1 and recorded in `data/MANIFEST.md`.

---

## Increment 2 — not needed yet, listed so you can start the slow ones early

Copernicus registrations in particular can take a day, and each dataset needs its own
licence click-through *after* the account exists.

| # | Source | Where | Unblocks | Note |
|---|---|---|---|---|
| 3 | **Google Earth Engine** | <https://earthengine.google.com/signup/> | MAIAC AOD, Sentinel-5P, VIIRS fire, land cover, GHSL | **Highest leverage.** Server-side reduction means no raster touches your 14 GB of free disk. Needs a Google Cloud project. |
| 4 | **Copernicus ADS** | <https://ads.atmosphere.copernicus.eu/> | CAMS reanalysis + CAMS forecasts | Required for the mandated "beat raw CAMS" baseline. Separate from CDS below. |
| 5 | **Copernicus CDS** | <https://cds.climate.copernicus.eu/> | ERA5, ERA5-Land | Per-dataset licence acceptance required. |
| 6 | **NASA Earthdata** | <https://urs.earthdata.nasa.gov/users/new> | MERRA-2, direct MAIAC/VIIRS | Redundant with GEE for most uses; useful as a fallback. |

### Why Earth Engine is the one to do first

The naive pipeline downloads rasters and extracts station values locally. MAIAC at 1 km
over five countries across several years is on the order of hundreds of GB to a few TB —
it does not fit, and never will on this machine. Earth Engine's `reduceRegions` collapses
imagery to station-buffer statistics **server-side**, so what crosses the network is a
small table. That is both the only feasible path here and the more reproducible one, since
the archived artifact is a checksummable CSV rather than an unreproducible pile of HDFs.

---

## Not requested, and why

- **Uzhydromet / Kazhydromet national data** — no open API is known to exist. Phase 1 will
  document what is actually retrievable. If access requires a data-sharing request, that is
  a decision for you, not something to be assumed.
- **Anything requiring payment.** Nothing in this project should cost money. If a source
  turns out to be paywalled, it gets recorded as a limitation, not purchased.
