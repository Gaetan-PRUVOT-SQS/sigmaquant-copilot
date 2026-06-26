"""Module 05 — FFT Carr-Madan, calibration, Vasicek (from 05-computational.md)."""
import math
import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm


def _bs_call(S0, K, r, T, sigma, q=0.0):
    d1 = (math.log(S0 / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return math.exp(-q * T) * S0 * norm.cdf(d1) - math.exp(-r * T) * K * norm.cdf(d2)


def _heston_cf(u, params, S0, r, q, T):
    kappa = float(params["kappa"])
    theta = float(params["theta"])
    sigma_v = float(params["sigma_v"])
    rho = float(params["rho"])
    v0 = float(params["v0"])
    tmp = kappa - 1j * rho * sigma_v * u
    g = np.sqrt((sigma_v ** 2) * (u ** 2 + 1j * u) + tmp ** 2)
    pow1 = 2 * kappa * theta / (sigma_v ** 2)
    # Drift sous mesure risque-neutre avec portage (r − q), cohérent avec _gbm_cf.
    numer1 = (kappa * theta * T * tmp) / (sigma_v ** 2) + 1j * u * T * (r - q) + 1j * u * math.log(S0)
    # Forme log-stabilisée (« Little Heston Trap ») : log(cosh x + a·sinh x) = x + log((1+a)/2 +
    # (1-a)/2·e^{-2x}) avec x=gT/2, a=tmp/g. Évite l'overflow de cosh/sinh (NaN dès T≳10 ans).
    # np.sqrt donne Re(g)≥0 -> e^{-2x} borné, l'argument du log reste fini.
    x = g * T / 2.0
    a = tmp / g
    log_denum1 = pow1 * (x + np.log((1.0 + a) / 2.0 + (1.0 - a) / 2.0 * np.exp(-2.0 * x)))
    tmp2 = ((u * u + 1j * u) * v0) / (g / np.tanh(g * T / 2) + tmp)
    return np.exp(numer1 - log_denum1 - tmp2)


def _gbm_cf(u, params, S0, r, q, T):
    sig = float(params.get("sigma", params.get("sigma_v", 0.2)))
    mu = math.log(S0) + (r - q - sig ** 2 / 2) * T
    a = sig * math.sqrt(T)
    return np.exp(1j * mu * u - 0.5 * (a * u) ** 2)


def carr_madan(params: dict) -> dict:
    model = params.get("model", "heston")
    S0 = float(params["S0"])
    K = float(params["K"])
    r = float(params["r"])
    T = float(params["T"])
    q = float(params.get("q", 0))
    p = params.get("params", params)
    alpha = float(params.get("alpha", 1.5))
    eta = float(params.get("eta", 0.25))
    n = int(params.get("n", 12))
    if not (1 <= n <= 16):                       # garde-fou DoS : N = 2**n (n=16 -> 65 536)
        raise ValueError("n (puissance de la grille FFT) doit être entre 1 et 16")
    if T <= 0 or eta <= 0:
        raise ValueError("T et eta doivent être positifs")
    N = 2 ** n
    lda = (2 * np.pi / N) / eta
    beta = math.log(K)
    nu_j = np.arange(N) * eta
    df = math.exp(-r * T)

    if model == "heston":
        cf = lambda u: _heston_cf(u, p, S0, r, q, T)
    else:
        cf = lambda u: _gbm_cf(u, p, S0, r, q, T)

    psi = cf(nu_j - (alpha + 1) * 1j) / ((alpha + 1j * nu_j) * (alpha + 1 + 1j * nu_j))
    w = np.full(N, eta)
    w[0] = eta / 2
    x = np.exp(-1j * beta * nu_j) * df * psi * w
    y = np.fft.fft(x)
    km = beta + lda * np.arange(N)
    prices = (np.exp(-alpha * km) / math.pi) * np.real(y)
    call = float(prices[0])
    if not math.isfinite(call):   # garde-fou : pas de NaN/Inf silencieux (domaine de validité)
        raise ValueError("Prix FFT non fini — modèle/paramètres hors domaine (ex. explosion de moments)")
    return {
        "call": round(call, 6),
        "strike": K,
        "model": model,
        "grid": {"N": N, "eta": eta, "lambda": round(lda, 6), "alpha": alpha},
    }


def calibrate(params: dict) -> dict:
    """Calibrate a model to an option surface by minimizing RMSE (real optimizer loop).

    `quotes` may be an explicit surface [[K, price], ...] priced at (S0, r, T); if it is a path
    string or missing, a synthetic surface is generated from known parameters so the loop has a
    target to fit. GBM fits the flat vol σ; Heston fits (θ, v0) with (κ, σ_v, ρ) held fixed.
    Returns the fitted parameters, achieved RMSE and optimizer diagnostics.
    """
    model = params.get("model", "heston")
    optimizer = params.get("optimizer", "nelder-mead")
    S0 = float(params.get("S0", 100)); r = float(params.get("r", 0.05)); T = float(params.get("T", 1))
    quotes = params.get("quotes")

    if isinstance(quotes, (list, tuple)) and quotes and isinstance(quotes[0], (list, tuple)):
        strikes = [float(k) for k, _ in quotes]
        market = [float(p) for _, p in quotes]
        source = "provided"
    else:
        strikes = [90.0, 100.0, 110.0]
        if model == "heston":
            truth = {"kappa": 2, "theta": 0.04, "sigma_v": 0.3, "rho": -0.7, "v0": 0.04}
            market = [carr_madan({"model": "heston", "S0": S0, "K": k, "r": r, "T": T,
                                  "n": 10, "params": truth})["call"] for k in strikes]
        else:
            market = [_bs_call(S0, k, r, T, 0.20) for k in strikes]
        source = "synthetic"

    if model == "heston":
        fixed = {"kappa": 2, "sigma_v": 0.3, "rho": -0.7}
        names = ["theta", "v0"]; x0 = [0.06, 0.06]

        def model_prices(x):
            p = dict(fixed, theta=abs(x[0]), v0=abs(x[1]))
            return [carr_madan({"model": "heston", "S0": S0, "K": k, "r": r, "T": T,
                                "n": 10, "params": p})["call"] for k in strikes]
    else:
        names = ["sigma"]; x0 = [0.30]

        def model_prices(x):
            return [_bs_call(S0, k, r, T, abs(x[0])) for k in strikes]

    def rmse_of(x):
        mp = model_prices(x)
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(mp, market)) / len(market))

    res = minimize(rmse_of, x0, method="Nelder-Mead",
                   options={"xatol": 1e-6, "fatol": 1e-9, "maxiter": 200})
    return {
        "status": "calibrated",
        "model": model,
        "optimizer": optimizer,
        "surface": source,
        "n_quotes": len(strikes),
        "fitted_params": {n: float(round(abs(float(v)), 6)) for n, v in zip(names, res.x)},
        "rmse": round(float(res.fun), 8),
        "n_iter": int(res.nit),
        "success": bool(res.success),
        "objective": "min_Theta sqrt(mean((V_model - V_market)^2))",
    }


def _vasicek_zcb(r0, theta_bar, kappa, sigma, T):
    B = T if kappa <= 0 else (1 - math.exp(-kappa * T)) / kappa
    A = math.exp((theta_bar - sigma ** 2 / (2 * kappa ** 2)) * (B - T) - (sigma ** 2 * B ** 2) / (4 * kappa))
    return A * math.exp(-B * r0)


def vasicek(params: dict) -> dict:
    """Fit a Vasicek short-rate model to a market ZCB curve (real optimizer loop).

    ZCB closed form P(0,T) = A(T)·e^{-B(T)·r0}. `curve` may be [[T, yield], ...]; a path string or
    missing input falls back to a synthetic upward curve. With (κ, σ) held fixed, (r0, θ̄) are
    fitted so model ZCB prices match the market, returning fitted params, RMSE and model prices.
    """
    kappa = float(params.get("kappa", 0.5))
    sigma = float(params.get("sigma", 0.01))
    curve = params.get("curve")

    if isinstance(curve, (list, tuple)) and curve and isinstance(curve[0], (list, tuple)):
        mats = [float(t) for t, _ in curve]
        mkt = [math.exp(-float(y) * float(t)) for t, y in curve]
        source = "provided"
    else:
        mats = [1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
        ylds = [0.030 + 0.004 * math.log(1 + t) for t in mats]  # gently upward curve
        mkt = [math.exp(-y * t) for y, t in zip(ylds, mats)]
        source = "synthetic"

    def rmse_of(x):
        r0, theta_bar = x
        model = [_vasicek_zcb(r0, theta_bar, kappa, sigma, t) for t in mats]
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(model, mkt)) / len(mats))

    res = minimize(rmse_of, [0.03, 0.03], method="Nelder-Mead",
                   options={"xatol": 1e-8, "fatol": 1e-12, "maxiter": 500})
    r0f, thf = res.x
    return {
        "status": "calibrated",
        "kappa": kappa,
        "sigma": sigma,
        "curve": source,
        "fitted": {"r0": round(float(r0f), 6), "theta_bar": round(float(thf), 6)},
        "rmse": round(float(res.fun), 10),
        "n_iter": int(res.nit),
        "success": bool(res.success),
        "maturities": mats,
        "model_zcb": [round(_vasicek_zcb(r0f, thf, kappa, sigma, t), 6) for t in mats],
    }