"""Module 02 — Credit & term structure: CDS, lattice ZCB, mortgage, survival."""
import math


def hazard_survival(params: dict) -> dict:
    hazard = float(params["hazard"])
    t = float(params["t"])
    q = math.exp(-hazard * t)
    return {"survival": round(q, 6), "default_prob": round(1 - q, 6)}


def mortgage(params: dict) -> dict:
    M0 = float(params["M0"])
    c = float(params["c"])
    n = int(params["n"])
    if c <= 0 or n <= 0:
        raise ValueError("Monthly rate c and n must be positive")
    if n > 12000:                                  # garde-fou : (1+c)**n -> OverflowError
        raise ValueError("n (nombre de mensualités) doit être ≤ 12000")
    factor = (1 + c) ** n
    payment = c * factor * M0 / (factor - 1)
    return {"monthly_payment": round(payment, 2), "total_paid": round(payment * n, 2)}


def cds(params: dict) -> dict:
    """CDS par spread = protection leg / risky PV01.

    Flat hazard λ (survival S(t)=e^{-λt}) and flat continuous discount r. The premium leg is
    a discrete schedule (default quarterly) with accrual-on-default; the protection leg pays
    (1-R) at default. Both legs use survival and discounting, so the spread responds to the
    hazard, recovery, discount rate and tenor — not just the credit-triangle approximation.
    """
    h = float(params["hazard"])
    R = float(params["recovery"])
    r = float(params.get("rate", 0.03))
    tenor = float(params.get("tenor_years", 5))
    freq = int(params.get("freq", 4))  # premium payments per year
    if h < 0 or not (0 <= R <= 1) or tenor <= 0 or freq <= 0:
        raise ValueError("hazard≥0, 0≤recovery≤1, tenor>0, freq>0 requis")
    n = max(int(round(tenor * freq)), 1)
    if n > 2000:                                   # garde-fou DoS : boucle de n périodes
        raise ValueError("tenor_years × freq doit être ≤ 2000")
    dt = tenor / n
    prem01 = 0.0   # risky PV01 of the premium leg (incl. accrual on default)
    prot = 0.0     # protection leg PV
    prev_surv = 1.0
    for i in range(1, n + 1):
        t = i * dt
        surv = math.exp(-h * t)
        df = math.exp(-r * t)
        dPD = prev_surv - surv               # default probability in (t_{i-1}, t]
        prem01 += dt * df * surv             # premium paid while alive
        prem01 += 0.5 * dt * df * dPD        # accrual on default (~half period)
        prot += df * (1 - R) * dPD           # protection payout at default
        prev_surv = surv
    spread = prot / prem01 if prem01 > 0 else 0.0
    return {
        "par_spread_annual": round(spread, 6),
        "par_spread_bps": round(spread * 10000, 2),
        "protection_leg": round(prot, 6),
        "risky_pv01": round(prem01, 6),
        "hazard": h,
        "recovery": R,
        "tenor_years": tenor,
        "discount_rate": r,
        "premium_freq": freq,
    }


def zcb_lattice(params: dict) -> dict:
    """ILLUSTRATIVE binomial short-rate lattice ZCB — NOT calibrated to a market curve.

    Uses a fixed q=0.5 and an ad-hoc multiplicative rate tree (r0·u^j·d^{i-j}); it is a teaching
    lattice, not an arbitrage-free pricer. For marking, calibrate the tree to observed ZCB/cap
    prices (Ho-Lee/BDT) first. The output carries `calibrated: false` to make this explicit.
    """
    r0 = float(params["r0"])
    periods = int(params["periods"])
    if not (1 <= periods <= 512):                  # garde-fou DoS/IndexError : arbre O(periods²)
        raise ValueError("periods doit être entre 1 et 512")
    face = float(params.get("face", 100))
    u, d, q = 1.25, 0.9, 0.5
    # terminal values
    layer = [face] * (periods + 1)
    for i in range(periods - 1, -1, -1):
        nxt = []
        for j in range(i + 1):
            r_node = r0 * (u ** (j)) * (d ** (i - j))
            r_node = max(r_node, 1e-6)
            cont = (q * layer[j + 1] + (1 - q) * layer[j]) / (1 + r_node)
            nxt.append(cont)
        layer = nxt
    return {"zcb_price": round(layer[0], 4), "periods": periods, "face": face,
            "calibrated": False, "note": "illustrative uncalibrated tree (q=0.5)"}