### D-005 — QC applied to the live hourly panel
- **Date:** 2026-07-28
- **Decision:** applied pre-registered QC rules Q1-Q7
- **Reason:** rules declared in data/DECISIONS.md before data inspection
- **Effect on n:** stations 11 -> 10, observations 450817 -> 340439
- **Alternative considered:** see FlatlinePolicy in qc/rules.py
- **Direction of bias if wrong:** rejecting whole stations preferentially removes low-cost sensors, and in this region that means removing whole cities -- which tightens F3.

| rule | scope | station | verdict | n_total | n_flagged | % | detail |
|---|---|---|---|---:|---:|---:|---|
| Q5b | station | `8225,8827` | **flag** | 2 | 2 | 100.00 | 2 location_ids within 150 m -- probably one instrument, providers: AirNow, StateAir Bishkek |
| Q5b | station | `8170,8870` | **flag** | 2 | 2 | 100.00 | 2 location_ids within 150 m -- probably one instrument, providers: AirNow, StateAir Ashgabat |
| Q4 | station | `8225` | **pass** | 52503 | 0 | 0.00 | median=17.00 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `8225` | **pass** | 52503 | 0 | 0.00 | span=5.99y (need 2.0), completeness=75.5% (need 60%) |
| Q4 | station | `8827` | **pass** | 46889 | 0 | 0.00 | median=15.00 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `8827` | **pass** | 46889 | 0 | 0.00 | span=5.35y (need 2.0), completeness=79.3% (need 60%) |
| Q4 | station | `8876` | **pass** | 49074 | 0 | 0.00 | median=15.00 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `8876` | **pass** | 49074 | 0 | 0.00 | span=5.60y (need 2.0), completeness=76.9% (need 60%) |
| Q4 | station | `7094` | **pass** | 57883 | 0 | 0.00 | median=14.00 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `7094` | **reject** | 57883 | 57883 | 100.00 | span=6.60y (need 2.0), completeness=42.8% (need 60%) |
| Q4 | station | `9769` | **pass** | 47077 | 0 | 0.00 | median=37.00 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `9769` | **pass** | 47077 | 0 | 0.00 | span=5.37y (need 2.0), completeness=77.0% (need 60%) |
| Q4 | station | `8684` | **pass** | 59160 | 0 | 0.00 | median=39.00 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `8684` | **pass** | 59160 | 0 | 0.00 | span=6.75y (need 2.0), completeness=83.3% (need 60%) |
| Q4 | station | `1894632` | **pass** | 21252 | 0 | 0.00 | median=21.70 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `1894632` | **pass** | 21252 | 0 | 0.00 | span=2.42y (need 2.0), completeness=68.3% (need 60%) |
| Q4 | station | `1924313` | **pass** | 21068 | 0 | 0.00 | median=28.60 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `1924313` | **pass** | 21068 | 0 | 0.00 | span=2.40y (need 2.0), completeness=79.1% (need 60%) |
| Q4 | station | `8170` | **pass** | 47078 | 0 | 0.00 | median=18.00 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `8170` | **pass** | 47078 | 0 | 0.00 | span=5.37y (need 2.0), completeness=68.2% (need 60%) |
| Q4 | station | `8870` | **pass** | 51790 | 0 | 0.00 | median=18.00 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `8870` | **pass** | 51790 | 0 | 0.00 | span=5.91y (need 2.0), completeness=65.3% (need 60%) |
| Q4 | station | `8881` | **pass** | 54926 | 0 | 0.00 | median=29.00 ug/m3, expected [1.0, 500.0] |
| Q7 | station | `8881` | **pass** | 54926 | 0 | 0.00 | span=6.27y (need 2.0), completeness=80.2% (need 60%) |
| Q6 | station | `8225` | **flag** | 39629 | 0 | 0.00 | diurnal shape does not match the region (r=0.32 at lag +1h); could be a genuinely different source regime rather than a timezone error -- inspect before deciding |
| Q6 | station | `8827` | **flag** | 37170 | 0 | 0.00 | diurnal shape does not match the region (r=0.34 at lag +0h); could be a genuinely different source regime rather than a timezone error -- inspect before deciding |
| Q6 | station | `8876` | **flag** | 37750 | 0 | 0.00 | diurnal shape does not match the region (r=0.31 at lag +1h); could be a genuinely different source regime rather than a timezone error -- inspect before deciding |
| Q6 | station | `9769` | **pass** | 36243 | 0 | 0.00 | aligned within 1h (lag +0h, r=0.84) |
| Q6 | station | `8684` | **pass** | 49305 | 0 | 0.00 | aligned within 1h (lag +0h, r=0.89) |
| Q6 | station | `1894632` | **flag** | 14525 | 0 | 0.00 | apparent +12h shift (r=0.70) is NOT IDENTIFIABLE: the regional reference self-correlates at r=0.71 under the same rotation, because the diurnal cycle is bimodal. Physical features disagree with the shift (min offset +11h, max offset -13h). Flagged for inspection, NOT rejected -- see data/DECISIONS.md D-006. |
| Q6 | station | `1924313` | **flag** | 16674 | 0 | 0.00 | apparent +12h shift (r=0.60) is NOT IDENTIFIABLE: the regional reference self-correlates at r=0.71 under the same rotation, because the diurnal cycle is bimodal. Physical features disagree with the shift (min offset +11h, max offset -13h). Flagged for inspection, NOT rejected -- see data/DECISIONS.md D-006. |
| Q6 | station | `8170` | **pass** | 32125 | 0 | 0.00 | aligned within 1h (lag +0h, r=0.97) |
| Q6 | station | `8870` | **pass** | 33827 | 0 | 0.00 | aligned within 1h (lag +0h, r=0.96) |
| Q6 | station | `8881` | **flag** | 44073 | 0 | 0.00 | apparent +11h shift (r=0.51) is NOT IDENTIFIABLE: the regional reference self-correlates at r=0.61 under the same rotation, because the diurnal cycle is bimodal. Physical features disagree with the shift (min offset +9h, max offset +1h). Flagged for inspection, NOT rejected -- see data/DECISIONS.md D-006. |
| Q1 | row | `8225` | **pass** | 52503 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `8225` | **pass** | 52503 | 0 | 0.00 | >=24 consecutive identical non-zero values |
| Q3 | row | `8225` | **pass** | 52503 | 0 | 0.00 | >=6 consecutive exact zeros |
| Q1 | row | `8827` | **pass** | 46889 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `8827` | **pass** | 46889 | 0 | 0.00 | >=24 consecutive identical non-zero values |
| Q3 | row | `8827` | **pass** | 46889 | 0 | 0.00 | >=6 consecutive exact zeros |
| Q1 | row | `8876` | **pass** | 49074 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `8876` | **pass** | 49074 | 0 | 0.00 | >=24 consecutive identical non-zero values |
| Q3 | row | `8876` | **pass** | 49074 | 0 | 0.00 | >=6 consecutive exact zeros |
| Q1 | row | `9769` | **pass** | 47077 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `9769` | **pass** | 47077 | 0 | 0.00 | >=24 consecutive identical non-zero values |
| Q3 | row | `9769` | **pass** | 47077 | 0 | 0.00 | >=6 consecutive exact zeros |
| Q1 | row | `8684` | **pass** | 59160 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `8684` | **flag** | 59160 | 94 | 0.16 | >=24 consecutive identical non-zero values |
| Q3 | row | `8684` | **pass** | 59160 | 0 | 0.00 | >=6 consecutive exact zeros |
| Q1 | row | `1894632` | **pass** | 21252 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `1894632` | **pass** | 21252 | 0 | 0.00 | >=24 consecutive identical non-zero values |
| Q3 | row | `1894632` | **pass** | 21252 | 0 | 0.00 | >=6 consecutive exact zeros |
| Q1 | row | `1924313` | **pass** | 21068 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `1924313` | **pass** | 21068 | 0 | 0.00 | >=24 consecutive identical non-zero values |
| Q3 | row | `1924313` | **pass** | 21068 | 0 | 0.00 | >=6 consecutive exact zeros |
| Q1 | row | `8170` | **pass** | 47078 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `8170` | **flag** | 47078 | 788 | 1.67 | >=24 consecutive identical non-zero values |
| Q3 | row | `8170` | **pass** | 47078 | 0 | 0.00 | >=6 consecutive exact zeros |
| Q1 | row | `8870` | **pass** | 51790 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `8870` | **pass** | 51790 | 0 | 0.00 | >=24 consecutive identical non-zero values |
| Q3 | row | `8870` | **pass** | 51790 | 0 | 0.00 | >=6 consecutive exact zeros |
| Q1 | row | `8881` | **pass** | 54926 | 0 | 0.00 | outside [0.0, 1000.0] ug/m3 |
| Q2 | row | `8881` | **pass** | 54926 | 0 | 0.00 | >=24 consecutive identical non-zero values |
| Q3 | row | `8881` | **pass** | 54926 | 0 | 0.00 | >=6 consecutive exact zeros |

**Stations rejected: 1** -- ['7094']