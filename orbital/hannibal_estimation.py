#!/usr/bin/env python3
"""
Section V Estimator -- Architecture of Accountability / Project Hannibal
==========================================================================
Pulls REAL data (FRED for CPI + M2 velocity, Yahoo Finance for Brent and
BDRY), builds the exact variable construction and non-linear threshold
model specified in Section 5.1-5.5 of the paper, and fits both the
additive and multiplicative-log specifications with Newey-West (HAC)
standard errors. Every number this prints is a real fitted result --
nothing here is a worked example with invented coefficients.

ONE-TIME SETUP
--------------
1. Get a free FRED API key (instant, no approval wait):
     https://fred.stlouisfed.org/docs/api/api_key.html
   You'll need a free FRED account first if you don't have one; the key
   request is a single form on your account page right after.

2. Set it as an environment variable (don't hardcode it in the script):
     Windows (PowerShell):  setx FRED_API_KEY "your-key-here"
                             (close and reopen the terminal afterward --
                              setx only takes effect in NEW windows)
     macOS/Linux:            export FRED_API_KEY="your-key-here"

RUN
---
    python hannibal_estimation.py

The first run installs its own Python packages (fredapi, yfinance,
statsmodels, pandas, numpy) automatically.

OUTPUT
------
Printed regression tables for both specifications, the coefficient of
interest (the threshold interaction term) called out explicitly with
its p-value, and a CSV of the full aligned dataset + threshold flags
written next to this script for your own inspection or re-plotting.
"""

import os
import subprocess
import sys


def _pip_install(pkg):
    print(f"Installing {pkg} (one-time)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])


try:
    import numpy as np
except ImportError:
    _pip_install("numpy")
    import numpy as np

try:
    import pandas as pd
except ImportError:
    _pip_install("pandas")
    import pandas as pd

try:
    from fredapi import Fred
except ImportError:
    _pip_install("fredapi")
    from fredapi import Fred

try:
    import yfinance as yf
except ImportError:
    _pip_install("yfinance")
    import yfinance as yf

try:
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import acorr_breusch_godfrey
except ImportError:
    _pip_install("statsmodels")
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import acorr_breusch_godfrey


# --- Config -----------------------------------------------------------
FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
if not FRED_API_KEY:
    try:  # same key the orbital [M] screen uses: OS credential store via hannibal_fred
        from hannibal_fred import get_key as _stored_fred_key
        FRED_API_KEY = _stored_fred_key()
    except Exception:  # noqa: BLE001
        FRED_API_KEY = ""
if not FRED_API_KEY:
    print("FRED_API_KEY is not set.")
    print("Get a free key:  https://fred.stlouisfed.org/docs/api/api_key.html")
    print('Then:  setx FRED_API_KEY "your-key-here"   (Windows, new terminal after)')
    print('  or:  export FRED_API_KEY="your-key-here"  (macOS/Linux)')
    sys.exit(1)

# ~7 years back, so after the 24-month warm-up there's roughly the
# ~60-observation regression sample the paper's own power discussion
# assumes (Section 6.5). Change freely -- it's just a starting point.
START_DATE = (pd.Timestamp.today().normalize() - pd.DateOffset(years=7)).strftime("%Y-%m-01")
WARMUP_MONTHS = 24     # Section 5.2
THRESHOLD_Q = 0.90     # Section 5.2


# --- 1. Pull raw data ---------------------------------------------------
def pull_fred_series(series_id):
    fred = Fred(api_key=FRED_API_KEY)
    s = fred.get_series(series_id, observation_start=START_DATE)
    s.index = pd.to_datetime(s.index)
    return s


def pull_yahoo_monthly_avg(ticker):
    """Monthly average of daily closes -- Section 5.1 specifies E as
    'monthly-averaged from daily closes'; the same treatment is applied
    to BDRY for consistency. Handles both the flat-column and the
    MultiIndex-column shapes different yfinance versions return."""
    df = yf.download(ticker, start=START_DATE, progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError(
            f"Yahoo Finance returned no data for {ticker}. Check the ticker, "
            "your internet connection, or try again in a minute (rate limits)."
        )
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"][ticker] if ticker in df["Close"].columns else df["Close"].iloc[:, 0]
    else:
        close = df["Close"]
    monthly = close.resample("MS").mean()
    monthly.index = pd.to_datetime(monthly.index)
    return monthly


# --- 2. Variable construction (Section 5.1) -----------------------------
def build_panel():
    print("Pulling CPI (CPIAUCSL) and M2 velocity (M2V) from FRED...")
    cpi = pull_fred_series("CPIAUCSL")
    m2v = pull_fred_series("M2V")  # native frequency: quarterly

    print("Pulling Brent (BZ=F) and BDRY from Yahoo Finance...")
    brent = pull_yahoo_monthly_avg("BZ=F")
    bdry = pull_yahoo_monthly_avg("BDRY")

    # I_t = (CPI_t / CPI_{t-12}) - 1
    cpi_m = cpi.resample("MS").last()
    I = (cpi_m / cpi_m.shift(12) - 1).rename("I")

    # M: growth computed on the native QUARTERLY series first, THEN
    # forward-filled to monthly -- Section 5.1 is explicit that doing
    # this the other way round produces a false staircase pattern.
    m2v_q = m2v.resample("QS").last()
    m2v_growth_q = m2v_q.pct_change()
    M = m2v_growth_q.resample("MS").ffill().rename("M")

    # E: MoM % change in monthly-averaged Brent
    E = brent.pct_change().rename("E")

    # T: MoM % change in BDRY
    T = bdry.pct_change().rename("T")

    panel = pd.concat([I, E, T, M], axis=1)
    panel = panel.loc[START_DATE:]
    return panel


# --- 3. Non-linear threshold (Section 5.2) ------------------------------
def add_threshold(panel):
    q90 = panel["E"].expanding(min_periods=WARMUP_MONTHS).quantile(THRESHOLD_Q)
    panel = panel.copy()
    panel["Q90_boundary"] = q90
    th = (panel["E"] > q90).astype(float)
    th[q90.isna()] = np.nan  # undefined during warm-up -- NOT "no shock"
    panel["th"] = th
    panel["E_th"] = panel["E"] * panel["th"]
    panel["E_T"] = panel["E"] * panel["T"]
    panel["E_M"] = panel["E"] * panel["M"]
    return panel


# --- 4. HAC lag selection (Section 5.5) ---------------------------------
def select_hac_lag(y, X, max_lag=12):
    """Breusch-Godfrey LM test at increasing lags; return the smallest
    lag at which residual autocorrelation is no longer significant
    (p > 0.05)."""
    plain_fit = sm.OLS(y, X).fit()
    for lag in range(1, max_lag + 1):
        lm_stat, lm_pvalue, f_stat, f_pvalue = acorr_breusch_godfrey(
            plain_fit, nlags=lag, result_object=False
        )
        if lm_pvalue > 0.05:
            return lag, lm_pvalue
    return max_lag, None  # never cleared within the tested range


# --- 5. Fit both specifications (Section 5.3 / 5.4) ---------------------
def fit_additive(panel):
    cols = ["I", "E", "E_th", "T", "M", "E_T", "E_M"]
    sample = panel[cols].dropna()
    y = sample["I"]
    X = sm.add_constant(sample[["E", "E_th", "T", "M", "E_T", "E_M"]])
    hac_lag, bg_p = select_hac_lag(y, X)
    model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lag})
    return model, sample, hac_lag, bg_p


def fit_log(panel, additive_sample):
    log_df = pd.DataFrame(index=additive_sample.index)
    log_df["ln1_I"] = np.log1p(additive_sample["I"])
    log_df["ln1_E"] = np.log1p(additive_sample["E"])
    log_df["ln1_T"] = np.log1p(additive_sample["T"])
    log_df["ln1_M"] = np.log1p(additive_sample["M"])
    log_df["ln1_E_th"] = log_df["ln1_E"] * panel.loc[additive_sample.index, "th"]
    log_df["ln1_E_T"] = log_df["ln1_E"] * log_df["ln1_T"]

    y = log_df["ln1_I"]
    X = sm.add_constant(log_df[["ln1_E", "ln1_E_th", "ln1_T", "ln1_M", "ln1_E_T"]])
    hac_lag, bg_p = select_hac_lag(y, X)
    model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lag})
    return model


# --- 6. Report ------------------------------------------------------------
def report(name, model, coef_of_interest, hac_lag, bg_p, n_obs):
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    print(f"Observations: {n_obs}   HAC lag: {hac_lag} (Breusch-Godfrey p={bg_p})")
    print(model.summary())
    if coef_of_interest in model.params.index:
        b = model.params[coef_of_interest]
        p = model.pvalues[coef_of_interest]
        print(f"\n>>> Coefficient of interest ({coef_of_interest}): {b:.5f}  (p={p:.4f})")
        if p < 0.05 and b > 0:
            print(">>> Significant AND positive: consistent with convex (non-linear)")
            print(">>> pass-through above the Q90 threshold.")
        elif p < 0.05:
            print(">>> Significant but NOT positive: does not support the paper's")
            print(">>> convexity hypothesis as specified.")
        else:
            print(">>> Not statistically significant at the 5% level: this sample")
            print(">>> gives no evidence of non-linear pass-through.")


def main():
    panel = build_panel()
    panel = add_threshold(panel)

    n_flagged = int(panel["th"].sum(skipna=True))
    print(f"\nAligned monthly panel: {len(panel)} rows, "
          f"{panel.index.min().date()} to {panel.index.max().date()}")
    print(f"Shock months flagged (E_t > expanding Q90, "
          f"after {WARMUP_MONTHS}-mo warm-up): {n_flagged}")

    additive_model, additive_sample, hac_lag, bg_p = fit_additive(panel)
    report("ADDITIVE MODEL (Section 5.3)", additive_model, "E_th",
           hac_lag, bg_p, len(additive_sample))

    log_model = fit_log(panel, additive_sample)
    log_hac_lag, log_bg_p = select_hac_lag(
        log_model.model.endog, log_model.model.exog
    )
    report("MULTIPLICATIVE LOG MODEL (Section 5.4)", log_model, "ln1_E_th",
           log_hac_lag, log_bg_p, len(additive_sample))

    print(f"\n{'=' * 70}")
    print("REMINDER -- Section 5.6 guardrails, unchanged by this run:")
    print("  - This is association, not an identified causal effect (no instruments).")
    print(f"  - {len(additive_sample)} monthly observations: limited power to confirm")
    print("    a true structural break vs. a temporary regime.")
    print("  - BDRY is an equity-ETF proxy for freight, not a pure freight-rate index.")
    print("=" * 70)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "hannibal_estimation_results.csv")
    panel.to_csv(out_path)
    print(f"\nFull aligned dataset + threshold flags written to:\n  {out_path}")


if __name__ == "__main__":
    main()
