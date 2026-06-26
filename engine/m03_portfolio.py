"""Module 03 — Portfolio & execution: CAPM, Sharpe, Almgren-Chriss (linear impact)."""
import math


def capm(params: dict) -> dict:
    rf = float(params["rf"])
    beta = float(params["beta"])
    mrp = float(params["mrp"])
    er = rf + beta * mrp
    return {
        "expected_return": round(er, 6),
        "expected_return_pct": round(er * 100, 4),
    }


def sharpe(params: dict) -> dict:
    Rp = float(params["Rp"])
    rf = float(params["rf"])
    sigma = float(params["sigma"])
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    s = (Rp - rf) / sigma
    return {"sharpe": round(s, 6)}


def almgren(params: dict) -> dict:
    """Almgren-Chriss optimal liquidation trajectory with linear temporary impact.

    Closed-form holdings path x(t) = X·sinh(κ(T−t))/sinh(κT) with κ = √(λσ²/η), where λ is risk
    aversion (rho), σ the volatility, η the temporary-impact coefficient. As λ→0 the path
    degenerates to TWAP (linear); higher λ front-loads trading. The schedule is split into
    `steps` intervals (default 10), so it is non-degenerate even for a 1-period horizon.
    """
    X = float(params["shares"])
    sigma = float(params.get("sigma", 0.02))
    lam = float(params.get("rho", 1e-6))      # risk aversion λ
    T = float(params.get("T", 1))
    eta = float(params.get("eta", 1e-4))      # temporary-impact coefficient
    N = max(int(params.get("steps", 10)), 1)
    if N > 10000:                                  # garde-fou DoS : trajectoire de N pas
        raise ValueError("steps doit être ≤ 10000")
    if T <= 0:
        raise ValueError("Horizon T must be positive")
    tau = T / N
    kappa = math.sqrt(lam * sigma ** 2 / eta) if eta > 0 else 0.0

    def holdings(t):
        if kappa * T < 1e-9:                   # risk-neutral limit → TWAP
            return X * (1 - t / T)
        return X * math.sinh(kappa * (T - t)) / math.sinh(kappa * T)

    trajectory = []
    cost = 0.0
    risk = 0.0
    prev = X
    for k in range(1, N + 1):
        x = holdings(k * tau)
        n_k = prev - x                         # shares traded in interval k
        cost += eta * (n_k ** 2) / tau         # temporary-impact cost
        risk += (sigma ** 2) * (x ** 2) * tau  # variance of remaining inventory
        trajectory.append({"step": k, "trade": round(n_k, 2), "remaining": round(max(x, 0), 2)})
        prev = x

    return {
        "trajectory": trajectory,
        "kappa": round(kappa, 6),
        "total_cost_proxy": round(cost, 4),
        "risk_penalty": round(lam * risk, 6),
        "objective": round(cost + lam * risk, 6),
    }