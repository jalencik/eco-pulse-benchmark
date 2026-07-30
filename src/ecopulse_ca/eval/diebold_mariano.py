"""Diebold-Mariano test for equal forecast accuracy.

"Model A has 0.3 lower RMSE" is not a finding. Forecast errors are serially correlated --
strongly so for h-step-ahead predictions of an autocorrelated field like PM2.5 -- so a naive
paired t-test on the loss differential badly understates its variance and turns noise into
significance. DM applies a HAC (Newey-West) correction with the truncation lag set from the
forecast horizon, which is the specific thing that makes it appropriate here.

Two details that are easy to omit and change conclusions:

- **Harvey-Leybourne-Newbold small-sample correction.** The asymptotic DM statistic
  over-rejects in finite samples. HLN rescales it and refers to a t-distribution with n-1
  degrees of freedom. With one year of daily-aggregated comparisons (~365 points) this is
  not negligible.

- **The truncation lag must be h-1, not 0.** An h-step-ahead forecast error is an MA(h-1)
  process even under the null of optimality, so autocorrelation up to lag h-1 is expected
  rather than evidence against the model.

The test says nothing about which model is *better in practice* -- only whether the observed
difference in expected loss is distinguishable from zero.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class DMResult:
    statistic: float
    p_value: float
    n: int
    horizon_hours: int
    mean_loss_diff: float
    better: str
    significant_at_05: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "dm_stat": self.statistic,
            "p_value": self.p_value,
            "n": self.n,
            "horizon_hours": self.horizon_hours,
            "mean_loss_diff": self.mean_loss_diff,
            "better": self.better,
            "significant_at_05": self.significant_at_05,
        }

    def verdict(self, name_a: str, name_b: str) -> str:
        if np.isnan(self.p_value):
            return f"{name_a} vs {name_b}: not computable"
        if not self.significant_at_05:
            return (
                f"{name_a} vs {name_b}: no significant difference "
                f"(DM={self.statistic:+.2f}, p={self.p_value:.3f})"
            )
        winner = name_a if self.better == "a" else name_b
        return (
            f"{name_a} vs {name_b}: **{winner} better** "
            f"(DM={self.statistic:+.2f}, p={self.p_value:.4f})"
        )


def newey_west_variance(d: np.ndarray, lags: int) -> float:
    """Long-run variance of the loss differential with a Bartlett kernel."""
    n = d.size
    d_centred = d - d.mean()
    gamma0 = float(np.dot(d_centred, d_centred) / n)
    total = gamma0
    for lag in range(1, min(lags, n - 1) + 1):
        cov = float(np.dot(d_centred[lag:], d_centred[:-lag]) / n)
        weight = 1.0 - lag / (lags + 1.0)
        total += 2.0 * weight * cov
    return total


def newey_west_bandwidth(n: int) -> int:
    """Standard automatic truncation lag, floor(4 * (n/100)^(2/9))."""
    return int(np.floor(4 * (n / 100) ** (2 / 9)))


#: Minimum truncation lag for hourly series with no forecast horizon (nowcasting).
#: PM2.5 loss differentials carry diurnal structure, so the HAC window should span at
#: least one full cycle even when the automatic rule suggests less.
MIN_NOWCAST_LAG_HOURS = 24


def nowcast_truncation_lag(n: int) -> int:
    """Truncation lag for a nowcasting comparison, which has no h to derive one from.

    Nowcasting is not h-step-ahead, so the MA(h-1) argument that justifies `lag = h-1` for
    forecasts does not apply. But the loss differential is still strongly autocorrelated --
    measured at r = 0.45 at lag 1 h on this benchmark -- so a zero lag (no HAC correction
    at all) badly overstates significance. Uses the larger of the standard automatic
    bandwidth and one diurnal cycle.
    """
    return max(newey_west_bandwidth(n), MIN_NOWCAST_LAG_HOURS)


def diebold_mariano(
    obs: pd.Series,
    pred_a: pd.Series,
    pred_b: pd.Series,
    horizon_hours: int = 24,
    loss: str = "squared",
    hln_correction: bool = True,
    truncation_lag: int | None = None,
) -> DMResult:
    """Test whether forecasts `a` and `b` have equal expected loss.

    Negative statistic favours `a` (its loss is lower). Returns NaN results rather than
    raising when the comparison is degenerate -- identical forecasts, or too few points --
    because a degenerate comparison is a legitimate outcome that must be reported, not an
    error to swallow.
    """
    frame = pd.concat([obs.rename("obs"), pred_a.rename("a"), pred_b.rename("b")], axis=1).dropna()
    n = len(frame)
    if n < 10:
        return DMResult(float("nan"), float("nan"), n, horizon_hours, float("nan"), "?", False)

    e_a = frame["a"].to_numpy(float) - frame["obs"].to_numpy(float)
    e_b = frame["b"].to_numpy(float) - frame["obs"].to_numpy(float)
    if loss == "squared":
        d = e_a**2 - e_b**2
    elif loss == "absolute":
        d = np.abs(e_a) - np.abs(e_b)
    else:
        raise ValueError(f"unknown loss {loss!r}")

    mean_d = float(d.mean())

    # Identical forecasts -- e.g. persistence vs diurnal persistence at multiples of 24h.
    # That is a real property of the ladder, reported rather than tested.
    if np.allclose(d, 0.0):
        return DMResult(0.0, 1.0, n, horizon_hours, 0.0, "tie", False)

    lags = truncation_lag if truncation_lag is not None else max(0, horizon_hours - 1)
    lrv = newey_west_variance(d, lags)
    if lrv <= 0:
        return DMResult(float("nan"), float("nan"), n, horizon_hours, mean_d, "?", False)

    stat = mean_d / np.sqrt(lrv / n)

    if hln_correction:
        h = lags + 1
        factor = (n + 1 - 2 * h + h * (h - 1) / n) / n
        stat *= np.sqrt(max(factor, 1e-12))
        p = float(2 * (1 - stats.t.cdf(abs(stat), df=n - 1)))
    else:
        p = float(2 * (1 - stats.norm.cdf(abs(stat))))

    return DMResult(
        statistic=float(stat),
        p_value=p,
        n=n,
        horizon_hours=horizon_hours,
        mean_loss_diff=mean_d,
        better="a" if mean_d < 0 else "b",
        significant_at_05=bool(p < 0.05),
    )


def pairwise_dm(
    obs: pd.Series,
    predictions: dict[str, pd.Series],
    horizon_hours: int = 24,
    truncation_lag: int | None = None,
) -> pd.DataFrame:
    """Every ordered pair of models, so the results table can state what is separable."""
    names = sorted(predictions)
    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            r = diebold_mariano(
                obs,
                predictions[a],
                predictions[b],
                horizon_hours,
                truncation_lag=truncation_lag,
            )
            rows.append(
                {
                    "model_a": a,
                    "model_b": b,
                    "truncation_lag": r.horizon_hours if truncation_lag is None else truncation_lag,
                    **r.as_dict(),
                }
            )
    return pd.DataFrame(rows)


def lag_sensitivity(
    obs: pd.Series,
    pred_a: pd.Series,
    pred_b: pd.Series,
    lags: tuple[int, ...] = (0, 24, 48, 168, 336),
) -> pd.DataFrame:
    """Re-run the test across truncation lags.

    A conclusion that flips with the lag choice is not a conclusion. Reporting the
    sensitivity makes that visible instead of hiding it behind one convenient setting.
    """
    rows = []
    for lag in lags:
        r = diebold_mariano(obs, pred_a, pred_b, truncation_lag=lag)
        rows.append(
            {
                "truncation_lag_h": lag,
                "dm_stat": r.statistic,
                "p_value": r.p_value,
                "significant_at_05": r.significant_at_05,
            }
        )
    return pd.DataFrame(rows)
