# Data Access Registration

Every predictor source in this project sits behind a free account and a licence
click-through. This file lists what to register for, in the order that actually unblocks
work, and what each one gives you.

Before anything else, the important part: **you do not need any of this to check the
benchmark.** The splits are committed and hashed, and the test suite runs offline against
committed fixtures. Registration only matters if you want to rebuild the panel from source.

Once you have a key, put it in `.env` (copy `.env.example`). `.env` is gitignored and it
should never end up in a notebook, a commit, or a log line.

---

## Required to rebuild the panel

### 1. OpenAQ v3 API key, the only real blocker

- Register at <https://explore.openaq.org/register>, free.
- The key arrives by email and authenticates through an `X-API-Key` header.
- Put it in `.env` as `OPENAQ_API_KEY=...`
- **Unblocks:** all ground-truth ingestion, QC, split construction, and the whole
  credential-free baseline ladder. It does not unblock the learned model or the CAMS
  comparison, which additionally need the two predictor-layer accounts below.

Until that key exists the ingestion client runs against committed offline fixtures, so the
test suite still passes. No number derived from a fixture is ever reported as a result.

### 2. US Embassy / State Department monitors

The historical PM2.5 files for Tashkent, Astana, Almaty, Bishkek and Dushanbe were published
as direct downloads. Both original hosts are dead now (`stateair.net` refuses connections and
`dosairnowdata.org` no longer resolves), so in practice these feeds are reached through
OpenAQ, and what survives at the original source survives through the Internet Archive.
`data/MANIFEST.md` records what was retrievable and when. If you do end up needing the AirNow
API directly, the key is at <https://docs.airnowapi.org/account/request/>.

---

## Needed for the predictor layer

Copernicus registrations in particular can take a day, and each dataset needs its own licence
accepted *after* the account exists, so start those early if you plan to go that far.

| # | Source | Where | Unblocks | Note |
|---|---|---|---|---|
| 3 | **Google Earth Engine** | <https://earthengine.google.com/signup/> | MAIAC AOD, Sentinel-5P, VIIRS fire, land cover, GHSL | **Highest leverage.** Server-side reduction means no raster ever touches your disk. Needs a Google Cloud project. |
| 4 | **Copernicus ADS** | <https://ads.atmosphere.copernicus.eu/> | CAMS reanalysis and CAMS forecasts | Required for the "beat raw CAMS" baseline. Separate account from CDS below. |
| 5 | **Copernicus CDS** | <https://cds.climate.copernicus.eu/> | ERA5, ERA5-Land | Per-dataset licence acceptance required. |
| 6 | **NASA Earthdata** | <https://urs.earthdata.nasa.gov/users/new> | MERRA-2, direct MAIAC/VIIRS | Mostly redundant with Earth Engine, useful as a fallback. |

### Why Earth Engine is the one to do first

The naive pipeline downloads rasters and extracts the station values locally. MAIAC at 1 km
over five countries across several years is somewhere between hundreds of gigabytes and a few
terabytes. It does not fit, and it was never going to fit on the machine this was built on,
which had 14 GB free. Earth Engine's `reduceRegions` collapses the imagery to station-buffer
statistics **server-side**, so what crosses the network is a small table.

Also that turned out to be the more reproducible path anyway, because the archived artifact
is a checksummable CSV instead of an unreproducible pile of HDF files.

---

## Not requested, and why

- **Uzhydromet and Kazhydromet national data.** No open API is known to exist for either.
  `data/MANIFEST.md` documents what was actually retrievable. If access needs a formal
  data-sharing request then that is a decision for a human to make, not something to assume.
- **Anything that costs money.** Nothing in this project should cost anything. If a source
  turns out to be paywalled it gets recorded as a limitation instead of purchased.
