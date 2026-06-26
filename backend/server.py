#!/usr/bin/env python3
"""Back-end local de SigmaQuant Copilot (app de bureau).

Démarre `llama-server` (llama.cpp) sur le modèle GGUF embarqué EN ARRIÈRE-PLAN, et expose
immédiatement un petit serveur HTTP (pour pouvoir remonter une erreur de démarrage au lieu de
rester bloqué silencieusement) :

  GET  /health        -> {"ready": bool, "model": str, "error": str|null}
  POST /ask {question}-> {"final": str, "engine": <result|null>, "error": <str|null>}

`/ask` rejoue exactement la logique de `run.py` : le modèle route la question et émet un
bloc ```engine```, et le moteur déterministe (paquet `engine/`) calcule le nombre exact.

Config par variables d'environnement (posées par le process Rust de Tauri) :
  SQSL_ROOT/MODEL/SYSTEM_PROMPT, SQSL_LLAMA_BIN, SQSL_LLAMA_LIBDIR (DYLD), SQSL_BACKEND_PORT.
  SQSL_LLAMA_PORT n'est qu'une préférence : si le port est occupé, on en choisit un libre.
"""
import atexit
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("SQSL_ROOT", Path(__file__).resolve().parents[1]))
MODEL = Path(os.environ.get("SQSL_MODEL", ROOT / "models" / "sqsl-2.0-Q4_K_M.gguf"))
SYSP_PATH = Path(os.environ.get("SQSL_SYSTEM_PROMPT", ROOT / "prompts" / "system_fr.txt"))
LLAMA_BIN = os.environ.get("SQSL_LLAMA_BIN", "llama-server")
BACKEND_PORT = int(os.environ.get("SQSL_BACKEND_PORT", "8765"))
CTX = int(os.environ.get("SQSL_CTX", "4096"))
MAX_BODY = 1 << 20  # 1 Mo : borne le corps des requêtes

# État de démarrage remonté via /health (au lieu d'un blocage silencieux).
STATE = {"startup_error": None, "llama_error": None}

# Prompt système : chargé tôt mais sans tuer le process s'il manque (on le signale).
try:
    SYSP = SYSP_PATH.read_text(encoding="utf-8").strip()
except Exception as e:  # noqa: BLE001
    SYSP = None
    STATE["startup_error"] = f"prompt système introuvable ({SYSP_PATH}) : {e}"


def _pick_port(preferred: int) -> int:
    """Renvoie `preferred` s'il est libre, sinon un port éphémère libre (évite la collision 8080)."""
    for cand in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", cand))
                return s.getsockname()[1]
        except OSError:
            continue
    return preferred


LLAMA_PORT = _pick_port(int(os.environ.get("SQSL_LLAMA_PORT", "8080")))
LLAMA_URL = f"http://127.0.0.1:{LLAMA_PORT}"

# Réutilise le moteur déterministe existant (source de vérité de chaque nombre).
# Frozen (PyInstaller) : `engine` est bundlé. Dev : importable via le dossier du script.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(ROOT))
from engine.integrate import enrich_response, guard_output, under_specified  # noqa: E402
from engine.router import parse_engine_block  # noqa: E402

_llama_proc = None


def log(*a):
    print("[backend]", *a, flush=True)


# --------------------------------------------------------------------------- llama.cpp lifecycle
def start_llama():
    global _llama_proc
    if not MODEL.exists():
        raise FileNotFoundError(f"Modèle introuvable : {MODEL}")
    cmd = [
        LLAMA_BIN, "-m", str(MODEL),
        "--chat-template", "chatml",
        "--host", "127.0.0.1", "--port", str(LLAMA_PORT),
        "-c", str(CTX), "-ngl", "999",
    ]
    env = os.environ.copy()
    libdir = os.environ.get("SQSL_LLAMA_LIBDIR")  # dylibs du llama embarqué (app empaquetée)
    if libdir:
        prev = env.get("DYLD_LIBRARY_PATH", "")
        env["DYLD_LIBRARY_PATH"] = libdir + (":" + prev if prev else "")
    log("démarrage llama-server :", " ".join(cmd))
    _llama_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)


def stop_llama():
    global _llama_proc
    if _llama_proc and _llama_proc.poll() is None:
        log("arrêt llama-server")
        _llama_proc.terminate()
        try:
            _llama_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _llama_proc.kill()
    _llama_proc = None


_INITIAL_PPID = os.getppid()


def _watchdog():
    """Si le process parent (Rust/Tauri) meurt brutalement, on est reparenté (ppid change) :
    on tue alors llama-server et on quitte, pour ne pas laisser d'orphelin de 2,5 Go."""
    while True:
        if os.getppid() != _INITIAL_PPID:
            stop_llama()
            os._exit(0)
        time.sleep(0.25)


def llama_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{LLAMA_URL}/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def boot_llama():
    """Démarre llama + attend le modèle, en arrière-plan. Toute erreur est mise dans STATE."""
    try:
        start_llama()
    except Exception as e:  # noqa: BLE001
        STATE["llama_error"] = str(e)
        log("ERREUR démarrage llama :", e)
        return
    log(f"attente du modèle ({MODEL.name})…")
    for _ in range(180):  # ~3 min max pour charger 2,5 Go
        if llama_ready():
            log("modèle prêt.")
            return
        if _llama_proc and _llama_proc.poll() is not None:
            STATE["llama_error"] = "llama-server s'est arrêté pendant le chargement du modèle."
            log("ERREUR :", STATE["llama_error"])
            return
        time.sleep(1)
    STATE["llama_error"] = "le modèle n'a pas fini de charger dans le délai imparti."


def current_error():
    return STATE["startup_error"] or STATE["llama_error"]


# --------------------------------------------------------------------------- inference + engine
def call_model(question: str) -> str:
    payload = json.dumps({
        "messages": [{"role": "system", "content": SYSP},
                     {"role": "user", "content": question}],
        "temperature": 0,
        "max_tokens": 1024,
        "stop": ["<|im_end|>", "<|endoftext|>"],
    }).encode()
    req = urllib.request.Request(
        f"{LLAMA_URL}/v1/chat/completions", payload,
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def ask(question: str) -> dict:
    """Chaîne complète : question -> modèle -> bloc engine -> moteur déterministe."""
    raw = call_model(question)
    raw = guard_output(raw, SYSP)  # anti-fuite
    try:
        payload = parse_engine_block(raw)
    except Exception:
        payload = None
    if under_specified(question, payload):  # anti-fabrication
        return {
            "final": ("Il me manque les paramètres pour calculer. Précisez les valeurs "
                      "(p. ex. rendement, taux sans risque, volatilité)."),
            "engine": None, "error": None,
        }
    final, engine_out, err = enrich_response(raw)
    if err:
        log("engine error (interne, non exposé):", err)   # journal interne uniquement
    return {"final": final, "engine": engine_out.get("result") if engine_out else None, "error": None}


# --------------------------------------------------------------------------- HTTP server
class Handler(BaseHTTPRequestHandler):
    def _host_ok(self) -> bool:
        # Protection anti DNS-rebinding : on n'accepte que les hôtes loopback.
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost", "")

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            self._send(403, {"error": "host refusé"}); return
        if self.path.rstrip("/") == "/health":
            err = current_error()
            self._send(200, {"ready": err is None and llama_ready(), "model": MODEL.name, "error": err})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok():
            self._send(403, {"error": "host refusé"}); return
        if self.path.rstrip("/") != "/ask":
            self._send(404, {"error": "not found"}); return
        try:
            try:
                n = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self._send(400, {"error": "Content-Length invalide"}); return
            if n < 0 or n > MAX_BODY:
                self._send(413, {"error": "requête trop volumineuse"}); return
            body = json.loads(self.rfile.read(n) or b"{}")
            question = (body.get("question") or "").strip()
            if not question:
                self._send(400, {"error": "question vide"}); return
            err = current_error()
            if err:
                self._send(503, {"error": f"Moteur local indisponible : {err}"}); return
            if not llama_ready():
                self._send(503, {"error": "Le moteur local démarre encore, réessaie dans un instant."}); return
            self._send(200, ask(question))
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *a):  # silence le log stderr par défaut
        pass


def main():
    atexit.register(stop_llama)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: (stop_llama(), sys.exit(0)))

    threading.Thread(target=_watchdog, daemon=True).start()
    if STATE["startup_error"]:
        log("ERREUR démarrage :", STATE["startup_error"])
    else:
        threading.Thread(target=boot_llama, daemon=True).start()  # llama en arrière-plan

    srv = ThreadingHTTPServer(("127.0.0.1", BACKEND_PORT), Handler)
    log(f"back-end HTTP prêt sur http://127.0.0.1:{BACKEND_PORT} (llama sur :{LLAMA_PORT})")
    try:
        srv.serve_forever()
    finally:
        stop_llama()


if __name__ == "__main__":
    main()
