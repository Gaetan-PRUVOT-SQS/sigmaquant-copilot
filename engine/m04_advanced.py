"""Module 04 — Advanced pricing: Greeks, Breeden-Litzenberger, CDO tranche."""
import math
from scipy.stats import norm
from scipy.integrate import quad

from .m01_foundations import _d1_d2


def delta(params: dict) -> dict:
    d1 = float(params["d1"])
    q = float(params.get("q", 0.0))   # dividende/portage ; T requis pour le facteur e^{−qT}
    T = float(params.get("T", 0.0))
    disc = math.exp(-q * T)           # q=0 (défaut) -> 1, comportement inchangé
    nd1 = norm.cdf(d1)
    return {
        "delta_call": round(disc * nd1, 6),
        "delta_put": round(disc * (nd1 - 1), 6),
    }


def breeden_litzenberger(params: dict) -> dict:
    strikes = [float(x) for x in params["strikes"]]
    call_prices = [float(x) for x in params["call_prices"]]
    if len(strikes) < 3:
        raise ValueError("Need at least 3 strikes for finite differences")
    r = float(params.get("r", 0.05))
    T = float(params.get("T", 1))
    # find index nearest 100 if present
    target = float(params.get("target_strike", 100))
    idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - target))
    if idx == 0 or idx >= len(strikes) - 1:
        idx = len(strikes) // 2
    Km, Kp, Kmm = strikes[idx], strikes[idx + 1], strikes[idx - 1]
    Cm, Cp, Cmm = call_prices[idx], call_prices[idx + 1], call_prices[idx - 1]
    dK1, dK2 = Kp - Km, Km - Kmm
    d2C = (
        2 * ((Cp - Cm) / dK1 - (Cm - Cmm) / dK2) / (dK1 + dK2)
    )
    density = math.exp(r * T) * d2C
    return {
        "strike": Km,
        "risk_neutral_density": round(max(density, 0), 8),
    }


def cdo(params: dict) -> dict:
    """Homogeneous Gaussian copula — equity tranche expected loss (1-period approx)."""
    names = int(float(params["names"]))
    if not (1 <= names <= 500):                    # garde-fou DoS : comb(names,l) sur range(names+1) sous quad
        raise ValueError("names doit être entre 1 et 500")
    corr = float(params["corr"])
    if not (0 <= corr < 1):
        raise ValueError("corr (corrélation) doit être dans [0, 1)")
    tranche = params["tranche"]
    recovery = float(params.get("recovery", 0.4))
    L, U = float(tranche[0]), float(tranche[1])
    q = float(params.get("default_prob", 0.02))
    rho = corr
    R = recovery
    A = 1.0  # unit notional per name

    def binom_pmf(l, qm):
        from math import comb
        return comb(names, l) * (qm ** l) * ((1 - qm) ** (names - l))

    def tranche_loss(l_defaults):
        portfolio_loss = l_defaults * A * (1 - R) / names
        return max(min(portfolio_loss, U) - L, 0)

    def integrand(m):
        from math import exp, pi
        qm = norm.cdf((norm.ppf(q) - math.sqrt(rho) * m) / math.sqrt(1 - rho))
        el = sum(tranche_loss(l) * binom_pmf(l, qm) for l in range(names + 1))
        return el * math.exp(-0.5 * m * m) / math.sqrt(2 * math.pi)

    expected_loss, _ = quad(integrand, -8, 8, limit=100)
    return {
        "expected_tranche_loss": round(expected_loss, 6),
        "tranche": [L, U],
        "names": names,
        "correlation": corr,
    }