"""Online change-point detection on the dense streams that move before returns do.

Two detectors, both online (each point uses only what came before it):

* BOCPD (Adams & MacKay 2007) with a Normal-Gamma conjugate model: unknown mean and
  variance, Student-t predictive, constant hazard 1/H. Alarm when the posterior mass on a
  short run length (<= 2 points) exceeds P_ALARM after a warm-up.
* CUSUM (Page 1954), two-sided, on standardised residuals against the pre-shift level:
  alarm when the statistic exceeds h (in sigma units).

The streams (weekly, synthetic) are added to the actuals by track.py: quoted TAT, slot
booking lead and LLP kit quotes from the contracted shop and suppliers, and the monthly
unscheduled-removal rate. Shop visits themselves are ~10-30 a year, too sparse for CPD.

Everything here is a prototype on synthetic data.
"""
from __future__ import annotations

import math

import numpy as np

WEEKS_PER_MONTH = 4
P_ALARM = 0.5
WARMUP = 4


def bocpd(x, hazard: float = 1 / 26, mu0=None, kappa0: float = 1.0, alpha0: float = 1.0, beta0=None):
    """Run-length posterior for a stream with unknown mean and variance.

    Returns (p_short, r_map): the probability that the run length is <= 2 at each point,
    and the MAP run length. Both are online quantities."""
    x = np.asarray(x, float)
    n = len(x)
    mu0 = float(np.mean(x[:WARMUP])) if mu0 is None else float(mu0)
    beta0 = float(max(1e-3, np.var(x[:WARMUP]) * alpha0)) if beta0 is None else float(beta0)
    R = np.zeros(n + 1)
    R[0] = 1.0
    mu, kappa, alpha, beta = np.array([mu0]), np.array([kappa0]), np.array([alpha0]), np.array([beta0])
    p_short, r_map = np.zeros(n), np.zeros(n, int)
    for t in range(n):
        # Student-t predictive for every current run length
        df = 2 * alpha
        scale = np.sqrt(beta * (kappa + 1) / (alpha * kappa))
        z = (x[t] - mu) / scale
        pred = np.exp(math.lgamma(1) * 0 + (np.vectorize(math.lgamma)((df + 1) / 2) - np.vectorize(math.lgamma)(df / 2))
                      - 0.5 * np.log(df * np.pi) - np.log(scale) - (df + 1) / 2 * np.log1p(z * z / df))
        growth = R[: t + 1] * pred * (1 - hazard)
        cp = float((R[: t + 1] * pred * hazard).sum())
        newR = np.zeros(n + 1)
        newR[1 : t + 2] = growth
        newR[0] = cp
        s = newR.sum()
        R = newR / s if s > 0 else newR
        # posterior update of the sufficient statistics, run length 0 restarts at the prior
        mu_n = (kappa * mu + x[t]) / (kappa + 1)
        beta_n = beta + kappa * (x[t] - mu) ** 2 / (2 * (kappa + 1))
        mu, kappa, alpha, beta = (np.concatenate([[mu0], mu_n]), np.concatenate([[kappa0], kappa + 1]),
                                  np.concatenate([[alpha0], alpha + 0.5]), np.concatenate([[beta0], beta_n]))
        p_short[t] = R[:3].sum()
        r_map[t] = int(np.argmax(R[: t + 2]))
    return p_short, r_map


def bocpd_alarm(x, **kw) -> int | None:
    p_short, _ = bocpd(x, **kw)
    for t in range(WARMUP, len(x)):
        if p_short[t] > P_ALARM:
            return t
    return None


def cusum(x, mu0: float, sigma: float, k: float = 0.5, h: float = 4.0):
    """Two-sided CUSUM on (x - mu0) / sigma. Returns (s_up, s_down, alarm index or None)."""
    x = (np.asarray(x, float) - mu0) / max(1e-9, sigma)
    up = np.zeros(len(x)); dn = np.zeros(len(x))
    alarm = None
    for t in range(len(x)):
        up[t] = max(0.0, (up[t - 1] if t else 0.0) + x[t] - k)
        dn[t] = max(0.0, (dn[t - 1] if t else 0.0) - x[t] - k)
        if alarm is None and (up[t] > h or dn[t] > h):
            alarm = t
    return up, dn, alarm


def ma_sigma_alarm(x, window: int = 3, z: float = 3.0, baseline: int = 12) -> int | None:
    """The existing reliability alert: 3-month moving average against mean + 3 sigma of the
    baseline months."""
    x = np.asarray(x, float)
    if len(x) <= baseline:
        return None
    base = x[:baseline]
    thr = base.mean() + z * base.std(ddof=1)
    for t in range(baseline + window - 1, len(x)):
        if x[t - window + 1 : t + 1].mean() > thr:
            return t
    return None


def uer_arl(lam0: float, shift: float, months: int = 36, change_at: int = 18,
            runs: int = 500, seed: int = 7, k: float = 0.5, h: float = 4.0) -> dict:
    """Detection delay and false alarms of CUSUM against the 3-month MA + 3 sigma alert, on
    Poisson monthly unscheduled-removal counts with a persistent shift at change_at."""
    rng = np.random.default_rng(seed)
    res = {"cusum": {"delay": [], "false": 0, "missed": 0}, "ma3": {"delay": [], "false": 0, "missed": 0}}
    sig = math.sqrt(lam0)
    for _ in range(runs):
        lam = np.full(months, lam0); lam[change_at:] *= 1 + shift
        y = rng.poisson(lam)
        _, _, a = cusum(y[12:], lam0, sig, k, h)       # baseline year sets the level, monitoring starts month 12
        a = None if a is None else a + 12
        b = ma_sigma_alarm(y, baseline=12)
        for name, t in (("cusum", a), ("ma3", b)):
            if t is None:
                res[name]["missed"] += 1
            elif t < change_at:
                res[name]["false"] += 1
            else:
                res[name]["delay"].append(t - change_at)
    out = {}
    for name, r in res.items():
        d = r["delay"]
        out[name] = {"mean_delay": float(np.mean(d)) if d else None, "p_detect_12m": float(sum(1 for v in d if v < 12) / runs),
                     "false_alarm_rate": r["false"] / runs, "missed": r["missed"] / runs}
    out["setup"] = {"shift": shift, "lam0_per_month": lam0, "months": months, "change_at": change_at, "runs": runs}
    return out


# ---------------------------------------------------------------- synthetic dense streams

def synth_streams(p_base, p_truth, months: int, rng, change_month: float = 1.5) -> dict:
    """Weekly quotes as an operator would see them, from the contracted shop and suppliers.
    They react to the true world *before* the returns do: a shop that is filling up quotes
    longer TATs and later slots first. The shift happens at change_month (assumption)."""
    n = months * WEEKS_PER_MONTH
    c = int(round(change_month * WEEKS_PER_MONTH))
    k0, k1 = p_base.shops[0], p_truth.shops[0]
    tat0 = np.mean([q.tat for q in k0.quotes.values()]) * 4.33
    tat1 = np.mean([q.tat for q in k1.quotes.values()]) * 4.33
    kit0, kit1 = p_base.llp_kit_lead_months * 4.33, p_truth.llp_kit_lead_months * 4.33
    slot0 = 8.0                                        # weeks to the next free slot (no_source)
    slot1 = slot0 + 6.0 * (tat1 > tat0)                # a congested shop books later (no_source)
    lvl = lambda a, b: np.where(np.arange(n) < c, a, b)  # noqa: E731
    return {
        "weeks_per_month": WEEKS_PER_MONTH,
        "change_week": c if (tat1 != tat0 or kit1 != kit0) else None,
        "quoted_tat_weeks": np.round(lvl(tat0, tat1) + rng.normal(0, 0.8, n), 1).tolist(),
        "slot_lead_weeks": np.round(lvl(slot0, slot1) + rng.normal(0, 1.2, n), 1).tolist(),
        "kit_lead_weeks": np.round(lvl(kit0, kit1) + rng.normal(0, 1.5, n), 1).tolist(),
        "note": "合成データ。工場・サプライヤーの週次の回答値。混雑は見積もりと枠回答に先に出るという仮定（出典なし）",
    }


STREAMS = {
    "quoted_tat_weeks": ("工場の見積もり工期（週）", "新規入場の見積もり TAT。混雑すると先に延びる"),
    "slot_lead_weeks": ("枠の回答リード（週）", "次に取れる枠まで何週か。混雑すると先に延びる"),
    "kit_lead_weeks": ("LLP キット納期回答（週）", "サプライヤーの納期回答。逼迫すると先に延びる"),
}


NOISE = {"quoted_tat_weeks": 0.8, "slot_lead_weeks": 1.2, "kit_lead_weeks": 1.5}   # week-to-week noise of the quotes (assumption)


def detect_streams(streams: dict) -> dict:
    """Both detectors on every stream; alarms as week and month indices."""
    out = {}
    w = streams["weeks_per_month"]
    for name in STREAMS:
        x = np.asarray(streams[name], float)
        b = bocpd_alarm(x)
        mu0, sd0 = float(x[:WARMUP].mean()), float(max(NOISE[name], x[:WARMUP].std(ddof=1)))
        _, _, cu = cusum(x, mu0, sd0, h=5.0)
        first = min([t for t in (b, cu) if t is not None], default=None)
        # a material shift only: the level after the alarm must move by more than the noise
        if first is not None and abs(float(x[first:].mean()) - mu0) < NOISE[name]:
            first = None
        out[name] = {"bocpd_week": b, "cusum_week": cu, "week": first,
                     "month": None if first is None else first // w + 1,   # month index k (1-based, as track uses)
                     "level_before": mu0, "level_after": float(x[first:].mean()) if first is not None else None,
                     "shift_sigma": None if first is None else float((x[first:].mean() - mu0) / sd0)}
    return out
