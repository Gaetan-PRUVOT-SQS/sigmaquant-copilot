"""Module 01 — Foundations: BS, parity, forward, risk-neutral prob, perpetuity."""
import math
from scipy.stats import norm


def _d1_d2(S0, K, r, T, sigma, q=0.0):
    if T <= 0 or sigma <= 0:
        raise ValueError("T and sigma must be positive")
    d1 = (math.log(S0 / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def black_scholes(params: dict) -> dict:
    S0 = float(params["S0"])
    K = float(params["K"])
    r = float(params["r"])
    T = float(params["T"])
    sigma = float(params["sigma"])
    q = float(params.get("q", 0))
    d1, d2 = _d1_d2(S0, K, r, T, sigma, q)
    disc_s = math.exp(-q * T)
    disc_k = math.exp(-r * T)
    call = disc_s * S0 * norm.cdf(d1) - disc_k * K * norm.cdf(d2)
    put = disc_k * K * norm.cdf(-d2) - disc_s * S0 * norm.cdf(-d1)
    return {
        "call": round(call, 6),
        "put": round(put, 6),
        "d1": round(d1, 6),
        "d2": round(d2, 6),
    }


def put_call(params: dict) -> dict:
    P = float(params["P"])
    S = float(params["S"])
    K = float(params["K"])
    r = float(params["r"])
    T = float(params["T"])
    q = float(params.get("q", 0.0))   # rendement de dividende/portage (cohérent avec black_scholes)
    # Parité : C − P = S·e^{−qT} − K·e^{−rT}
    call = P + S * math.exp(-q * T) - K * math.exp(-r * T)
    return {"call": round(call, 6), "put": round(P, 6)}


def forward(params: dict) -> dict:
    S0 = float(params["S0"])
    r = float(params["r"])
    T = float(params["T"])
    q = float(params.get("q", 0.0))
    # Continuous compounding (carry r − q), consistent with the Black-Scholes module.
    F = S0 * math.exp((r - q) * T)
    return {"forward": round(F, 6), "compounding": "continuous"}


def risk_neutral(params: dict) -> dict:
    u = float(params["u"])
    d = float(params["d"])
    r = float(params["r"])
    if u <= d:
        raise ValueError("Require u > d for no-arbitrage")
    R = 1 + r
    # No-arbitrage requires d < 1+r < u, otherwise q falls outside [0, 1].
    if not (d < R < u):
        raise ValueError(f"No-arbitrage violated: need d < 1+r < u (got d={d}, 1+r={R}, u={u})")
    q = (R - d) / (u - d)
    return {"q_up": round(q, 6), "q_down": round(1 - q, 6)}


def perpetuity_pv(params: dict) -> dict:
    C = float(params["C"])
    r = float(params["r"])
    if r <= 0:
        raise ValueError("Discount rate r must be positive")
    pv = C / r
    return {"pv": round(pv, 6)}