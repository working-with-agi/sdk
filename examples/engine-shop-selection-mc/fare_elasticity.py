#!/usr/bin/env python3
"""How strongly do trunk passengers answer the fare? An estimate from Japanese public data.

  ln pax(route, month) = route x calendar-month effects + route trends (quadratic)
                         + b ln real airfare + g ln business cycle + quake (2011-03..06) [+ s ln seats]

  pax, seats   MLIT air transport statistics, annual report table 3 (route x month), 10 trunk routes
               (the 5 Haneda trunk routes, and 5 others without the 2012+ LCC bases)
  real airfare CPI item "航空運賃" / CPI all items (national, monthly)
  business     Cabinet Office composite index, coincident
  instrument   Dubai crude in yen, lagged 1, 3 and 6 months (a cost shifter for the 2SLS)

The fare index is national, so b is a market-level elasticity (every carrier's fares together),
identified from year-to-year swings of the index around route trends -- small swings (about
+/-5 % a year), so the estimate is weak. It is also biased toward zero twice over: fares rise
when demand is strong (revenue management), and on capped routes passengers cannot rise when
fares fall. The seats variant shows how much the seats on offer, rather than the fare, carry the
passengers. Data and sources: data/elasticity/ (sources.json).

  python fare_elasticity.py --out fleet/fare_elasticity.json
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "elasticity"
HANEDA = ("HND-CTS", "HND-ITM", "HND-FUK", "HND-OKA", "HND-KIX")
TARGET = ("HND-CTS", "HND-ITM", "HND-FUK", "HND-OKA", "FUK-OKA")
HAC_LAGS = 12


def load() -> pd.DataFrame:
    p = pd.read_csv(DATA / "route_month.csv")
    m = pd.read_csv(DATA / "monthly_indexes.csv").sort_values("ym")
    m["oil_yen"] = m.dubai_usd * m.jpy_per_usd
    for lag in (1, 3, 6):
        m[f"loil{lag}"] = np.log(m.oil_yen.shift(lag) / m.cpi_all)
    m["lfare"] = np.log(m.cpi_air / m.cpi_all)
    m["lci"] = np.log(m.ci_coincident)
    p["ym"] = p.year * 100 + p.month
    d = p.merge(m, on="ym")
    d["lpax"] = np.log(d.pax); d["lseats"] = np.log(d.seats); d["lf"] = d.pax / d.seats
    d["t"] = (d.year - 2006) + (d.month - 1) / 12
    d["quake"] = ((d.ym >= 201103) & (d.ym <= 201106)).astype(float)
    return d.dropna(subset=["lfare", "lci", "loil6"]).reset_index(drop=True)


def design(df: pd.DataFrame, trends: bool = True, seats: bool = False) -> pd.DataFrame:
    cols = {"lci": df.lci, "quake": df.quake}
    for r in sorted(df.route.unique()):
        k = (df.route == r).astype(float)
        for mo in range(1, 13):
            cols[f"fe_{r}_{mo}"] = k * (df.month == mo)
        if trends:
            cols[f"tr_{r}"] = k * df.t
            cols[f"tr2_{r}"] = k * df.t ** 2
    if seats:
        cols["lseats"] = df.lseats
    X = pd.DataFrame(cols)
    return X.loc[:, (X != 0).any()]


def fit(df: pd.DataFrame, label: str, trends: bool = True, seats: bool = False) -> dict:
    from linearmodels.iv import IV2SLS
    X = design(df, trends, seats)
    kw = {"cov_type": "kernel", "kernel": "bartlett", "bandwidth": HAC_LAGS}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ols = IV2SLS(df.lpax, X.assign(lfare=df.lfare), None, None).fit(**kw)
        iv = IV2SLS(df.lpax, X, df[["lfare"]], df[["loil1", "loil3", "loil6"]]).fit(**kw)
    fs = iv.first_stage.diagnostics
    out = {"sample": label, "n": int(len(df)), "routes": int(df.route.nunique()), "months": int(df.ym.nunique()),
           "ols": {"b": round(float(ols.params["lfare"]), 3), "se": round(float(ols.std_errors["lfare"]), 3)},
           "iv": {"b": round(float(iv.params["lfare"]), 3), "se": round(float(iv.std_errors["lfare"]), 3),
                  "first_stage_F": round(float(fs["f.stat"].iloc[0]), 1), "partial_R2": round(float(fs["partial.rsquared"].iloc[0]), 3)},
           "business_cycle_b": round(float(ols.params["lci"]), 3)}
    if seats:
        out["seats_b"] = round(float(ols.params["lseats"]), 3)
    return out


def build(out: Path | None = None) -> dict:
    d = load()
    pre = d[d.year <= 2019]
    post = d[(d.year <= 2019) | (d.year >= 2023)]
    rows = [fit(pre, "2006–2019、10 路線"),
            fit(pre[pre.route.isin(HANEDA)], "2006–2019、羽田の 5 路線"),
            fit(pre, "2006–2019、10 路線、路線の傾向なし", trends=False),
            fit(post, "2006–2019 と 2023–2025、10 路線"),
            fit(pre, "2006–2019、10 路線、座席を固定", seats=True),
            fit(pre[pre.lf < 0.70], "2006–2019、10 路線、搭乗率 0.70 未満の月"),
            fit(pre[pre.lf < 0.70], "2006–2019、搭乗率 0.70 未満の月、座席を固定", seats=True)]
    by_route = [{**fit(pre[pre.route == r], f"2006–2019、{r} だけ"), "route": r} for r in TARGET]
    swings = pre.drop_duplicates("ym").assign(real=lambda x: x.cpi_air / x.cpi_all).groupby("year").real.mean()
    ols = [r["ols"]["b"] for r in rows if "傾向なし" not in r["sample"]]
    result = {"rows": rows, "by_route": by_route,
              "real_fare_index_by_year": {int(k): round(float(v), 3) for k, v in swings.items()},
              "summary": {"ols_range_with_trends": [min(ols), max(ols)],
                          "reading": "路線の傾向を入れた OLS は −0.11〜−0.48。原油を使った 2SLS は符号も定まらない（弱い操作変数）。"
                                     "座席の弾力性は約 0.7 で、旅客は運賃より座席で決まっている。どちらの偏りも 0 に寄せる向き"
                                     "（需要が強いと運賃が上がる、枠で詰まった路線は運賃が下がっても旅客が増えない）なので、"
                                     "この推定は市場全体の弾力性の絶対値の下限としてしか読めない"},
              "sources": json.loads((DATA / "sources.json").read_text(encoding="utf-8"))}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--out", type=Path)
    r = build(a.parse_args(argv).out)
    for x in r["rows"] + r["by_route"]:
        print(f"{x['sample']}: OLS {x['ols']['b']} ({x['ols']['se']})  2SLS {x['iv']['b']} ({x['iv']['se']}, F {x['iv']['first_stage_F']})" + (f"  seats {x['seats_b']}" if "seats_b" in x else ""))
    print("real fare index by year", r["real_fare_index_by_year"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
