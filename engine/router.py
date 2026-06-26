"""Parse ```engine``` JSON from copilot output and dispatch to deterministic pricers."""
import json
import re
from typing import Any

from .registry import validate, REGISTRY
from . import m01_foundations as m01
from . import m02_credit as m02
from . import m03_portfolio as m03
from . import m04_advanced as m04
from . import m05_computational as m05

ENGINE_RE = re.compile(r"```engine\s*\n(.*?)\n```", re.S | re.I)

HANDLERS: dict[str, dict[str, Any]] = {
    "01": {
        "black_scholes": m01.black_scholes,
        "put_call": m01.put_call,
        "forward": m01.forward,
        "risk_neutral": m01.risk_neutral,
        "perpetuity_pv": m01.perpetuity_pv,
    },
    "02": {
        "cds": m02.cds,
        "zcb_lattice": m02.zcb_lattice,
        "mortgage": m02.mortgage,
        "hazard_survival": m02.hazard_survival,
    },
    "03": {
        "capm": m03.capm,
        "sharpe": m03.sharpe,
        "almgren": m03.almgren,
    },
    "04": {
        "delta": m04.delta,
        "breeden_litzenberger": m04.breeden_litzenberger,
        "cdo": m04.cdo,
    },
    "05": {
        "carr_madan": m05.carr_madan,
        "calibrate": m05.calibrate,
        "vasicek": m05.vasicek,
    },
}


_MATH_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*([*/])\s*(-?\d+(?:\.\d+)?)")


def _math_repl(m):
    a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
    try:
        v = a / b if op == "/" else a * b
    except ZeroDivisionError:
        return m.group(0)
    return repr(v)


def _eval_math_segment(text: str) -> str:
    cur = text
    for _ in range(3):            # quelques passes pour les opérations chaînées
        new = _MATH_RE.sub(_math_repl, cur)
        if new == cur:
            break
        cur = new
    return cur


def _sanitize_math(s: str) -> str:
    """Evaluate simple numeric expressions the model sometimes emits (e.g. "T": 9/12) into
    plain numbers, so the JSON parses. Only touches text OUTSIDE quoted strings — and is aware
    of backslash escapes (\\"), so an escaped quote inside a string no longer flips the in/out
    parity and corrupts string content."""
    result = []
    seg = []
    in_string = False
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if in_string:
            seg.append(c)
            if c == "\\" and i + 1 < n:           # garde l'échappement verbatim
                seg.append(s[i + 1]); i += 2; continue
            if c == '"':
                result.append("".join(seg)); seg = []; in_string = False
            i += 1
        else:
            if c == '"':
                result.append(_eval_math_segment("".join(seg)))   # math seulement hors string
                seg = ['"']; in_string = True; i += 1
            else:
                seg.append(c); i += 1
    # reste : string non terminée -> verbatim ; sinon segment hors-string -> math
    result.append("".join(seg) if in_string else _eval_math_segment("".join(seg)))
    return "".join(result)


def _extract_json_object(s: str) -> dict:
    """Find the first plausible {..} object containing module/function in a noisy string.

    Utilise json.JSONDecoder().raw_decode, qui gère correctement les accolades à l'intérieur
    des chaînes (plus de rejet de JSON valide) et parse en O(n) à partir de chaque candidat.
    Le nombre de candidats et la longueur sont bornés (anti-DoS sur sortie modèle bruitée)."""
    s = _sanitize_math(s).strip()
    if len(s) > 100_000:                           # borne anti-DoS
        s = s[:100_000]
    dec = json.JSONDecoder()
    try:
        obj = dec.decode(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    idx, starts = 0, 0
    while starts < 2000:                           # borne le nombre de positions essayées
        b = s.find("{", idx)
        if b == -1:
            break
        starts += 1
        try:
            obj, _end = dec.raw_decode(s, b)        # parse JSON-correct, ignore les '{' en string
            if isinstance(obj, dict) and ("module" in obj or "function" in obj):
                return obj
        except json.JSONDecodeError:
            pass
        idx = b + 1
    raise ValueError("Could not find valid engine JSON object")


def parse_engine_block(text: str) -> dict:
    m = ENGINE_RE.search(text)
    raw = m.group(1) if m else text

    payload = _extract_json_object(raw)

    # Normalize common model mistakes
    if "params" not in payload and "parameters" in payload:
        payload["params"] = payload.pop("parameters")
    if "params" not in payload:
        # Try to build params from other keys (very loose fallback)
        known = {"S0", "K", "r", "T", "sigma", "q", "rf", "beta", "mrp", "shares", "hazard", "recovery"}
        p = {k: payload[k] for k in list(payload.keys()) if k in known or k.lower() in known}
        if p:
            payload["params"] = p

    for key in ("module", "function", "params"):
        if key not in payload:
            raise ValueError(f"Engine JSON missing '{key}' (got keys: {list(payload.keys())[:8]})")
    if not isinstance(payload["params"], dict):
        raise ValueError("'params' must be a JSON object")

    # Normalize module to 2-digit string
    payload["module"] = str(payload["module"]).zfill(2) if str(payload["module"]).isdigit() else str(payload["module"])
    return payload


# Palliatif robustesse (finding MRM « routage 80 % ») : le modèle émet parfois une clé de
# paramètre synonyme -> KeyError -> aucun nombre. On mappe les synonymes courants vers la clé
# canonique attendue par chaque handler. Conservateur (par fonction, n'écrase jamais une clé
# canonique déjà présente). Améliore la disponibilité sans toucher au modèle.
_PARAM_ALIASES = {
    ("01", "black_scholes"): {"S0": ["spot", "S", "s0", "price", "underlying"], "K": ["strike", "k"],
                              "r": ["rate", "interest", "r_f"], "T": ["maturity", "tenor", "t", "time"],
                              "sigma": ["vol", "volatility", "sig", "iv"], "q": ["dividend", "div", "dividend_yield", "yield"]},
    ("01", "put_call"): {"P": ["put", "put_price", "p_price", "prix_put"], "S": ["spot", "S0", "s", "price", "underlying"],
                         "K": ["strike", "k"], "r": ["rate", "interest"], "T": ["maturity", "tenor", "t", "time"],
                         "q": ["dividend", "div", "dividend_yield"]},
    ("01", "forward"): {"S0": ["spot", "S", "s0", "price", "underlying"], "r": ["rate", "interest"],
                        "T": ["maturity", "tenor", "t", "time"], "q": ["dividend", "div", "dividend_yield"]},
    ("01", "risk_neutral"): {"u": ["up"], "d": ["down"], "r": ["rate", "interest"]},
    ("01", "perpetuity_pv"): {"C": ["coupon", "cashflow", "cash_flow", "payment", "c"], "r": ["rate", "discount", "discount_rate"]},
    ("02", "hazard_survival"): {"hazard": ["lambda", "intensity", "hazard_rate", "h", "default_intensity"], "t": ["T", "time", "maturity", "tenor"]},
    ("02", "mortgage"): {"M0": ["principal", "loan", "amount", "balance", "notional"], "c": ["monthly_rate", "rate", "c_monthly", "monthly"],
                         "n": ["months", "n_payments", "periods", "term", "nper"]},
    ("02", "cds"): {"hazard": ["lambda", "intensity", "hazard_rate", "h", "default_intensity"], "recovery": ["recovery_rate", "R", "rr"],
                    "rate": ["r", "discount", "discount_rate"], "tenor_years": ["tenor", "maturity", "T", "years"],
                    "freq": ["frequency", "payments_per_year", "n_per_year"]},
    ("02", "zcb_lattice"): {"r0": ["r", "rate", "short_rate", "r_0"], "periods": ["n", "steps", "periods_n"], "face": ["notional", "par", "face_value"]},
    ("03", "capm"): {"rf": ["r_f", "risk_free", "rate", "riskfree"], "beta": ["b", "β"],
                     "mrp": ["market_risk_premium", "premium", "erp", "market_premium", "risk_premium"]},
    ("03", "sharpe"): {"Rp": ["return", "portfolio_return", "r_p", "Ra", "rp", "ret"], "rf": ["r_f", "risk_free", "riskfree", "rate"],
                       "sigma": ["vol", "volatility", "std", "sig", "stdev"]},
    ("03", "almgren"): {"shares": ["X", "quantity", "qty", "size", "x"], "sigma": ["vol", "volatility"],
                        "rho": ["lambda", "risk_aversion", "lam", "aversion"], "T": ["horizon", "maturity", "time"],
                        "eta": ["impact", "temp_impact", "temporary_impact"], "steps": ["N", "n", "intervals"]},
    ("04", "delta"): {"d1": ["d_1", "D1"], "q": ["dividend", "div", "dividend_yield"], "T": ["maturity", "tenor", "t"]},
    ("04", "breeden_litzenberger"): {"strikes": ["K", "Ks", "strike"], "call_prices": ["calls", "C", "prices", "call"],
                                     "r": ["rate"], "T": ["maturity", "tenor"], "target_strike": ["target", "K0", "atm", "strike0"]},
    ("04", "cdo"): {"names": ["n_names", "num_names", "n", "N", "nb_names"], "corr": ["correlation", "rho", "ρ"],
                    "tranche": ["tranche_bounds", "attach_detach", "bounds"], "recovery": ["recovery_rate", "R", "rr"],
                    "default_prob": ["pd", "default_probability", "q", "p"]},
    ("05", "carr_madan"): {"S0": ["spot", "S", "s0", "price"], "K": ["strike", "k"], "r": ["rate", "interest"],
                           "T": ["maturity", "tenor", "t"], "q": ["dividend", "div", "dividend_yield"]},
}


def _normalize_params(module: str, function: str, params: dict) -> dict:
    aliases = _PARAM_ALIASES.get((module, function))
    if not aliases or not isinstance(params, dict):
        return params
    out = dict(params)
    for canonical, syns in aliases.items():
        if canonical in out:
            continue                       # clé canonique déjà présente -> on n'écrase pas
        for s in syns:
            if s in out:
                out[canonical] = out[s]    # garde aussi l'alias (les handlers ignorent l'extra)
                break
    return out


def dispatch(payload: dict) -> dict:
    module = str(payload["module"]).zfill(2) if len(str(payload["module"])) == 1 else str(payload["module"])
    function = payload["function"]
    params = payload["params"]
    validate(module, function)
    params = _normalize_params(module, function, params)
    fn = HANDLERS[module][function]
    result = fn(params)
    return {
        "module": module,
        "function": function,
        "params": params,
        "result": result,
    }


def run(copilot_text: str) -> dict:
    """Full pipeline: copilot response text -> validated numeric result."""
    payload = parse_engine_block(copilot_text)
    return dispatch(payload)


def get_allowed_functions() -> dict:
    """Return the whitelist of module -> allowed functions (for prompting / errors)."""
    return {k: sorted(list(v)) for k, v in REGISTRY.items()}