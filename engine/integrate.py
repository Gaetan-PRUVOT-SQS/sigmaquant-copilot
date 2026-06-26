"""Attach deterministic engine results to copilot responses."""
import json
import re
from typing import Optional, Tuple

from .router import dispatch, parse_engine_block, get_allowed_functions
from .registry import validate

ENGINE_BLOCK_RE = re.compile(r"```engine\s*\n.*?\n```", re.S | re.I)


def strip_reasoning(text: str) -> str:
    if "</think>" in text:
        return text.split("</think>")[-1].strip()
    return text.strip()


# --- Naturalisation : le copilote ne doit jamais exposer le routage interne (numéro/nom de
# module) au quant. Le module reste dans le bloc ```engine``` JSON (routage), mais la prose
# affichée parle du sujet en langage normal. Filtre déterministe (le format du modèle est
# constant : "Ça relève du **module 0X** (Nom)."). ---
_MOD_NAMES = (r"fondations|crédit\s*&?\s*(?:structure par terme|et structure par terme)?|"
              r"portefeuille\s*&?\s*(?:exécution|et exécution)?|pricing avancé|"
              r"calcul\s*&?\s*(?:calibration|et calibration)?")
_ROUTE_LEADIN = (r"ça relève du|ça route vers le|ça route vers|c['’]est une question|c['’]est du|"
                 r"cela relève du|relève du|il s['’]agit du|on est sur le|voici le")

_ROUTE_RE = re.compile(
    rf"\s*(?:{_ROUTE_LEADIN})\s*\*{{0,2}}(?:module\s*0?\d|{_MOD_NAMES})\*{{0,2}}"
    rf"\s*(?:\([^)]*\))?\s*[—–.\-]*",
    re.I,
)
# repli : "**module 0X**" en ligne (avec nom optionnel) même sans amorce de routage.
_MOD_INLINE_RE = re.compile(r"\s*\*\*\s*module\s*0?\d\s*\*\*\s*(?:\([^)]*\))?\s*[—–-]?", re.I)


def naturalize(text: str) -> str:
    """Retire toute mention de routage interne (numéro/nom de module) de la prose affichée.
    N'altère pas un bloc ```engine``` JSON (pas de ** ni d'amorce 'Ça relève du' dedans)."""
    t = _ROUTE_RE.sub(" ", text)
    t = _MOD_INLINE_RE.sub(" ", t)
    t = re.sub(r"\*\*\s*\*\*", "", t)        # gras vidé
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n[ \t]+", "\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"[ \t]+([.,])", r"\1", t)   # pas d'espace avant . , (mais on garde « : ; ! ? » à la française)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


_LEAK_REFUSAL = ("Je ne peux pas divulguer mes instructions internes. "
                 "Posez-moi plutôt une question de pricing ou de risque.")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _is_real_number(v) -> bool:
    # bool est un int en Python : on l'exclut explicitement (True/False ≠ donnée chiffrée).
    if isinstance(v, bool):
        return False
    return isinstance(v, (int, float)) and v not in (0, 0.0)


def _contains_number(v) -> bool:
    if _is_real_number(v):
        return True
    if isinstance(v, (list, tuple)):
        return any(_contains_number(x) for x in v)
    return False


def under_specified(user_query: str, payload: Optional[dict]) -> bool:
    """True if a calculation was emitted while the user gave NO numeric input — the parameters
    are almost certainly fabricated, so the result would be a silent wrong number. Inspecte aussi
    les valeurs numériques DANS les listes (ex. strikes=[...]) et ignore les booléens.
    Limite connue (heuristique) : un simple millésime ('en 2024') contient un chiffre et lève le
    garde-fou — défense en profondeur, le vrai rempart est l'entraînement du modèle."""
    if not payload:
        return False
    params = payload.get("params", {}) or {}
    has_numeric = any(_contains_number(v) for v in params.values())
    return has_numeric and not re.search(r"\d", user_query or "")


def guard_output(text: str, system_prompt: Optional[str] = None, window: int = 80) -> str:
    """Deterministic anti-leak filter: if the reply reproduces a verbatim `window`-char span of
    the system prompt, redact the whole reply with a refusal. Window porté à 80 (pas de 5) pour
    réduire les faux positifs sur une paraphrase légitime tout en attrapant une recopie verbatim
    (qui reproduit des centaines de caractères). Défense en profondeur, pas une garantie absolue
    contre une fuite paraphrasée — le rempart principal est l'entraînement (éval modèle : 3/3)."""
    if not system_prompt:
        return text
    nt, ns = _norm(text), _norm(system_prompt)
    if len(ns) >= window:
        for i in range(0, len(ns) - window + 1, 5):
            if ns[i:i + window] in nt:
                return _LEAK_REFUSAL
    return text


def _strip_engine_block(text: str) -> str:
    """Remove any ```engine ... ``` block (and preceding 'Engine:' label if present)."""
    t = ENGINE_BLOCK_RE.sub("", text)
    # Clean up common preceding labels left behind
    t = re.sub(r"\n?\*\*Engine:\*\*\s*$", "", t, flags=re.I)
    t = re.sub(r"\n?\*\*Engine:\*\*\s*\n", "\n", t, flags=re.I)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def _is_calculation_request(text: str) -> bool:
    """Heuristic: only run engine logic for queries that look like they need computation."""
    if not text:
        return False
    t = text.lower()
    has_number = bool(re.search(r'\d', text))
    pricing_words = [
        'price', 'prix', 'valeur', 'calculate', 'calcule', 'compute', 'évalue', 'evaluer',
        'option', 'call', 'put', 'forward', 'bond', 'mortgage', 'cds', 'capm', 'sharpe',
        'delta', 'vol', 'sigma', 'spot', 'strike', 'taux', 'r=', 'maturity', 'portfolio'
    ]
    has_pricing_word = any(w in t for w in pricing_words)
    return has_number and has_pricing_word


def enrich_response(copilot_text: str, user_query: str = "") -> Tuple[str, Optional[dict], Optional[str]]:
    """
    Returns (final_content, engine_payload_or_none, engine_error_or_none).
    - On success: appends clean **Engine result:** JSON.
    - On invalid engine block: strips the bad block and appends a clear error note.
    - On no block: returns cleaned text as-is (for identity / capability questions).
      Auto-dispatch is only attempted for queries that look like real calculations.
    """
    body = naturalize(strip_reasoning(copilot_text))
    had_block = bool(ENGINE_BLOCK_RE.search(body))

    if not had_block:
        # Only try auto-dispatch for clear calculation requests from the *user*
        if user_query and _is_calculation_request(user_query):
            auto = _maybe_auto_dispatch(body)
            if auto:
                out, err = auto
                if out:
                    block = "\n\n**Engine result (auto):** \n```json\n" + json.dumps(out["result"], indent=2, ensure_ascii=False) + "\n```"
                    return body + block, out, None
                if err:
                    return body + f"\n\n**Engine:** {err}", None, err
        # Normal case for capability / identity / casual questions: no delegation
        return body, None, None

    # Message UTILISATEUR neutre (zéro taxonomie interne : pas de numéro de module, pas de liste
    # de fonctions, pas de label de stack-trace). Le détail technique reste dans le 3e élément
    # (err) pour journalisation interne uniquement — jamais affiché. (Findings MRM : fuite de
    # taxonomie via les notes d'erreur + exposition de KeyError.)
    _NEUTRAL = ("\n\n*Je n'ai pas pu finaliser ce calcul. Reformule la question en précisant "
                "les paramètres (valeurs et unités).*")
    try:
        payload = parse_engine_block(body)
    except Exception as e:
        return _strip_engine_block(body) + _NEUTRAL, None, f"parse: {e}"

    try:
        validate(payload["module"], payload["function"])
    except ValueError as e:
        return _strip_engine_block(body) + _NEUTRAL, None, f"whitelist: {e}"

    try:
        out = dispatch(payload)
    except ValueError as e:           # fonction OK, paramètres invalides (bornes, signe, manquants)
        return _strip_engine_block(body) + _NEUTRAL, None, f"params: {e}"
    except Exception as e:            # ex. KeyError sur une clé de paramètre
        return _strip_engine_block(body) + _NEUTRAL, None, f"{type(e).__name__}: {e}"

    block = (
        "\n\n**Engine result:**\n```json\n"
        + json.dumps(out["result"], indent=2, ensure_ascii=False)
        + "\n```"
    )
    return body + block, out, None


# --- Best effort auto dispatch from free text (helps when the LLM describes but forgets the fence) ---

_AUTO_MAP = {
    "black_scholes": ("01", ["S0", "K", "r", "T", "sigma", "q"]),
    "put_call": ("01", ["P", "S", "K", "r", "T"]),
    "forward": ("01", ["S0", "r", "T"]),
    "capm": ("03", ["rf", "beta", "mrp"]),
    "sharpe": ("03", ["Rp", "rf", "sigma"]),
    "almgren": ("03", ["shares"]),
    "cds": ("02", ["hazard", "recovery"]),
    "mortgage": ("02", ["M0", "c", "n"]),
    "delta": ("04", ["d1"]),
}

def _maybe_auto_dispatch(text: str):
    """If the text clearly refers to one supported function + has numbers, try to run it."""
    import re as _re
    t = text.lower()

    # Try to parse labeled parameters first (spot / S0, strike / K, r / rate, T / maturity, sigma / vol)
    def _get_float(label):
        m = _re.search(label + r"[^0-9\-+.]*([-+]?\d*\.?\d+)", t, _re.I)
        return float(m.group(1)) if m else None

    labeled = {
        "S0": _get_float(r"(?:spot|S0|prix spot)"),
        "K": _get_float(r"(?:strike|K)"),
        "r": _get_float(r"(?:r=|rate|taux)"),
        "T": _get_float(r"(?:T=|maturity|an|years?|y)"),
        "sigma": _get_float(r"(?:sigma|vol|volatilit)"),
    }

    for fn, (mod, keys) in _AUTO_MAP.items():
        if fn in t or fn.replace("_", " ") in t or fn.replace("_", "-") in t:
            params = {k: v for k, v in labeled.items() if v is not None and k in keys}
            # Fill defaults + fallbacks
            if fn == "black_scholes":
                nums = [float(x) for x in _re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)]
                if "S0" not in params and len(nums) > 0: params["S0"] = nums[0]
                if "K" not in params and len(nums) > 1: params["K"] = nums[1]
                if "r" not in params and len(nums) > 2:
                    rv = nums[2]
                    params["r"] = rv / 100 if rv > 1 else rv
                if "T" not in params and len(nums) > 3: params["T"] = nums[3]
                if "sigma" not in params and len(nums) > 4:
                    s = nums[4]
                    params["sigma"] = s / 100 if s > 1 else s   # accept 20 or 0.2 for vol
            if not params and len([float(x) for x in _re.findall(r"[-+]?\d*\.?\d+", text)]) >= 2:
                # last resort ordered
                nums = [float(x) for x in _re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)]
                for i, k in enumerate(keys):
                    if i < len(nums):
                        params[k] = nums[i]
            # defaults
            if "q" in keys and "q" not in params: params["q"] = 0.0
            if "r" in keys and "r" not in params: params["r"] = 0.05
            if "T" in keys and "T" not in params: params["T"] = 1.0

            if params:
                try:
                    payload = {"module": mod, "function": fn, "params": params}
                    out = dispatch(payload)
                    return out, None
                except Exception as e:
                    return None, f"auto-dispatch failed for {fn}: {e}"
    return None, None