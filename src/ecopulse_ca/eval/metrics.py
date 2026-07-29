"""Evaluation metrics for both tasks.

Two decisions here are scientific rather than cosmetic:

**Exceedance is scored on daily means, not hourly values.** The WHO 2021 guideline of
15 ug/m3 is a *24-hour* guideline. Applying it to hourly values would score a different
quantity than the one the guideline defines, and would inflate the positive rate because
hourly peaks exceed daily means. Both observations and predictions are aggregated to local
calendar days before thresholding.

**R2 is computed against the observed mean of the evaluation block**, not against a
model-free baseline. That makes R2 comparable across folds only when the blocks share a
distribution -- which across six cities they do not. RMSE and MAE are the primary metrics;
R2 is reported because reviewers expect it, with this caveat attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

WHO_2021_PM25_24H = 15.0  # ug/m3
#: Minimum hourly observations required before a day's mean is used for exceedance scoring.
MIN_HOURS_PER_DAY = 18


@dataclass
class RegressionMetrics:
    n: int
    rmse: float
    mae: float
    bias: float
    r2: float
    median_ae: float

    def as_dict(self) -> dict[str, float]:
        return {
            "n": self.n, "rmse": self.rmse, "mae": self.mae,
            "bias": self.bias, "r2": self.r2, "median_ae": self.median_ae,
        }


@dataclass
class ExceedanceMetrics:
    n_days: int
    n_exceed_obs: int
    n_exceed_pred: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float

    def as_dict(self) -> dict[str, float]:
        return {
            "n_days": self.n_days, "n_exceed_obs": self.n_exceed_obs,
            "n_exceed_pred": self.n_exceed_pred, "tp": self.tp, "fp": self.fp,
            "fn": self.fn, "tn": self.tn, "precision": self.precision,
            "recall": self.recall, "f1": self.f1,
        }


def _aligned(obs: pd.Series, pred: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    both = pd.concat([obs.rename("obs"), pred.rename("pred")], axis=1).dropna()
    return both["obs"].to_numpy(float), both["pred"].to_numpy(float)


def regression_metrics(obs: pd.Series, pred: pd.Series) -> RegressionMetrics:
    y, yhat = _aligned(obs, pred)
    if y.size == 0:
        nan = float("nan")
        return RegressionMetrics(0, nan, nan, nan, nan, nan)

    err = yhat - y
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return RegressionMetrics(
        n=int(y.size),
        rmse=float(np.sqrt(np.mean(err**2))),
        mae=float(np.mean(np.abs(err))),
        bias=float(np.mean(err)),
        r2=float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
        median_ae=float(np.median(np.abs(err))),
    )


def to_daily_mean(series: pd.Series, tz: str | None = None) -> pd.Series:
    """Local-calendar daily means, requiring MIN_HOURS_PER_DAY observations.

    Local days matter: a UTC day boundary cuts a Central Asian night in half, splitting the
    overnight inversion peak across two "days" and understating both.
    """
    if series.empty:
        return series
    idx = pd.DatetimeIndex(series.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    if tz:
        idx = idx.tz_convert(tz)
    local = pd.Series(series.to_numpy(), index=idx)
    grouped = local.groupby(local.index.date)
    daily = grouped.mean()
    counts = grouped.count()
    return daily.where(counts >= MIN_HOURS_PER_DAY)


def exceedance_metrics(
    obs: pd.Series,
    pred: pd.Series,
    threshold: float = WHO_2021_PM25_24H,
    tz: str | None = None,
) -> ExceedanceMetrics:
    """Binary exceedance skill against the WHO 2021 24-hour guideline.

    Scored on daily means because the guideline is a 24-hour standard. A day is scored only
    when BOTH observed and predicted daily means exist with enough hourly coverage --
    otherwise a model that predicts nothing on hard days would score well by abstaining.
    """
    o = to_daily_mean(obs, tz)
    p = to_daily_mean(pred, tz)
    both = pd.concat([o.rename("obs"), p.rename("pred")], axis=1).dropna()
    if both.empty:
        return ExceedanceMetrics(0, 0, 0, 0, 0, 0, 0, float("nan"), float("nan"), float("nan"))

    oe = both["obs"].to_numpy() > threshold
    pe = both["pred"].to_numpy() > threshold
    tp = int(np.sum(oe & pe))
    fp = int(np.sum(~oe & pe))
    fn = int(np.sum(oe & ~pe))
    tn = int(np.sum(~oe & ~pe))

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    if np.isnan(precision) or np.isnan(recall) or (precision + recall) == 0:
        f1 = 0.0 if (tp + fp + fn) > 0 else float("nan")
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return ExceedanceMetrics(
        n_days=len(both), n_exceed_obs=int(oe.sum()), n_exceed_pred=int(pe.sum()),
        tp=tp, fp=fp, fn=fn, tn=tn,
        precision=precision, recall=recall, f1=f1,
    )


@dataclass
class SeedSpread:
    """Mean and std across seeds, with an explicit deterministic flag.

    A deterministic model has zero seed variance **by construction**, not by measurement.
    Reporting `0.000` without saying so implies five independent runs happened to agree,
    which would be a remarkable result rather than an arithmetic certainty.
    """

    metric: str
    values: list[float] = field(default_factory=list)
    deterministic: bool = True

    @property
    def mean(self) -> float:
        return float(np.mean(self.values)) if self.values else float("nan")

    @property
    def std(self) -> float:
        return float(np.std(self.values, ddof=0)) if self.values else float("nan")

    def format(self, digits: int = 3) -> str:
        if self.deterministic:
            return f"{self.mean:.{digits}f} (det.)"
        return f"{self.mean:.{digits}f} ± {self.std:.{digits}f}"
