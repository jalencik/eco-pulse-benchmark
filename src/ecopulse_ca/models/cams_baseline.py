"""CAMS baselines: raw, and the two legitimate debiased variants.

Why debiasing is necessary for an honest claim
----------------------------------------------
Measured on the extracted panel, raw CAMS is biased by a factor of ~7 ACROSS cities:

    Almaty    CAMS/observed 1.38   (over-predicts)
    Ashgabat                0.72
    Tashkent                0.57
    Khujand           0.54 / 0.41
    Bishkek                 0.40
    Dushanbe          0.22 / 0.21   (under-predicts fivefold)

The project spec mandates beating "raw CAMS as-is". That rung is trivially beatable, because
most of the gap is a FIXED PER-CITY OFFSET that any model with a city term removes for free.
Reporting "we beat raw CAMS" would therefore be a weak claim dressed as a strong one -- the
same failure as citing the Xinjiang random-CV R2 as a target.

So two debiased variants exist, and WHICH ONE IS LEGITIMATE DEPENDS ON THE TASK:

**`CamsDebiasedLocal` -- Task F only.** Subtracts the station's own mean bias, estimated on
the TRAIN block. Valid for forecasting at a monitored station, where local history exists.
**Illegal under leave-city-out**, because the held-out city contributes no labels from which
to estimate its bias -- using them would be exactly the leak the protocol forbids.

**`CamsDebiasedPooled` -- Task N legitimate.** Subtracts the mean bias of the TRAINING
cities. Uses no information from the held-out city, so it survives leave-city-out. This is
the genuinely hard reference: it asks whether a model beats "CAMS, corrected by what other
cities taught us".

If a model cannot beat the pooled variant, it has learned nothing CAMS did not already know.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BiasTable:
    """Per-station additive bias estimated on the training block only."""

    per_station: dict[str, float] = field(default_factory=dict)
    pooled: float = 0.0
    n_obs: dict[str, int] = field(default_factory=dict)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"station_id": s, "bias_ug_m3": round(b, 3), "n_train_obs": self.n_obs.get(s, 0)}
             for s, b in sorted(self.per_station.items())]
        )


def fit_bias(
    cams: pd.DataFrame,
    observed_daily: dict[str, pd.Series],
    train_end: pd.Timestamp,
    value_col: str = "cams_pm25_forecast",
) -> BiasTable:
    """Estimate additive CAMS bias per station, using the TRAIN block only.

    `train_end` is enforced here rather than assumed upstream: a bias fitted on the full
    record would smuggle test-period information into the reference every model is measured
    against, inflating the whole ladder without any model changing.
    """
    per_station: dict[str, float] = {}
    n_obs: dict[str, int] = {}
    for sid, obs in observed_daily.items():
        sub = cams[cams.station_id == sid].copy()
        if sub.empty:
            continue
        sub["d"] = pd.to_datetime(sub["time"]).dt.date
        joined = pd.DataFrame({"obs": obs}).join(
            sub.set_index("d")[[value_col]], how="inner"
        )
        joined = joined[joined.index <= train_end.date()]
        joined = joined.dropna()
        if len(joined) < 30:
            continue
        per_station[sid] = float((joined[value_col] - joined["obs"]).mean())
        n_obs[sid] = int(len(joined))

    pooled = float(np.mean(list(per_station.values()))) if per_station else 0.0
    return BiasTable(per_station=per_station, pooled=pooled, n_obs=n_obs)


def apply_local_debias(cams: pd.DataFrame, bias: BiasTable,
                       value_col: str = "cams_pm25_forecast") -> pd.Series:
    """Task F: subtract each station's own bias. Illegal under leave-city-out."""
    off = cams["station_id"].map(bias.per_station).fillna(bias.pooled)
    return cams[value_col] - off


def apply_pooled_debias(cams: pd.DataFrame, bias: BiasTable, held_out: set[str],
                        value_col: str = "cams_pm25_forecast") -> pd.Series:
    """Task N: subtract the mean bias of the TRAINING stations only.

    `held_out` is excluded from the average, so no label from the held-out city informs its
    own correction. That is what makes this variant survive leave-city-out.
    """
    train_biases = [b for s, b in bias.per_station.items() if s not in held_out]
    offset = float(np.mean(train_biases)) if train_biases else 0.0
    return cams[value_col] - offset
