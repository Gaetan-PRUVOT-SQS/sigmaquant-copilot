"""Whitelist: module -> allowed function names (matches copilot training contract)."""

REGISTRY = {
    "01": {
        "black_scholes", "put_call", "forward", "risk_neutral", "perpetuity_pv",
    },
    "02": {
        "cds", "zcb_lattice", "mortgage", "hazard_survival",
    },
    "03": {
        "capm", "sharpe", "almgren",
    },
    "04": {
        "delta", "breeden_litzenberger", "cdo",
    },
    "05": {
        "carr_madan", "calibrate", "vasicek",
    },
}


def validate(module: str, function: str) -> None:
    if module not in REGISTRY:
        raise ValueError(f"Unknown module '{module}' — expected 01–05")
    if function not in REGISTRY[module]:
        raise ValueError(
            f"Function '{function}' not allowed in module {module}. "
            f"Allowed: {sorted(REGISTRY[module])}"
        )