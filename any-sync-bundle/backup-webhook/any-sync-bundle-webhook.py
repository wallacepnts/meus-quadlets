#!/usr/bin/env python3
"""Recebe os webhooks de pre/post-backup do Zerobyte pro any-sync-bundle.

Para o stack inteiro (bundle+mongo+redis) antes do Restic rodar e religa
depois — ver any-sync-bundle/README.md e zerobyte/README.md. Só stdlib de
propósito (sem dependências pra instalar num script que roda direto no
host, fora de container).
"""
import hmac
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("ANY_SYNC_BUNDLE_WEBHOOK_PORT", "8765"))
TOKEN_PATH = os.environ.get(
    "ANY_SYNC_BUNDLE_WEBHOOK_TOKEN_FILE",
    os.path.expanduser("~/.config/any-sync-bundle-webhook/token"),
)
SECRET_HEADER = "X-Zerobyte-Hook-Secret"

UNITS = [
    "any-sync-bundle.service",
    "any-sync-mongo.service",
    "any-sync-bundle-redis.service",
]
# Start em ordem de dependência (mongo/redis antes do bundle, que os
# Requires=) — stop não precisa, systemctl para cada unit independente.
START_ORDER = ["any-sync-mongo.service", "any-sync-bundle-redis.service", "any-sync-bundle.service"]


def load_token() -> str:
    with open(TOKEN_PATH) as f:
        return f.read().strip()


def systemctl(*args: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "any-sync-bundle-webhook/1"

    def _send_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _authorized(self) -> bool:
        got = self.headers.get(SECRET_HEADER, "")
        try:
            want = load_token()
        except OSError:
            print(f"token file not readable: {TOKEN_PATH}", file=sys.stderr)
            return False
        return hmac.compare_digest(got, want)

    def _read_body(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        self._read_body()

        if self.path not in ("/hooks/any-sync-bundle/pre-backup", "/hooks/any-sync-bundle/post-backup"):
            self._send_json(404, {"error": "not found"})
            return

        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return

        if self.path == "/hooks/any-sync-bundle/pre-backup":
            self._handle_pre()
        else:
            self._handle_post()

    def _handle_pre(self) -> None:
        # Bloqueante de propósito: o Zerobyte só roda o Restic depois de
        # um 2xx aqui, então a resposta PRECISA esperar o stop terminar
        # de verdade (systemctl --user stop já bloqueia até parar).
        try:
            result = systemctl("stop", *UNITS, timeout=45)
        except subprocess.TimeoutExpired:
            self._send_json(500, {"error": "timeout stopping units"})
            return
        if result.returncode != 0:
            print(f"stop failed: {result.stderr}", file=sys.stderr)
            self._send_json(500, {"error": "stop failed", "detail": result.stderr})
            return
        self._send_json(200, {"ok": True, "action": "stopped"})

    def _handle_post(self) -> None:
        # Não-bloqueante de propósito: mongo/redis usam Notify=healthy,
        # então "systemctl start" só retorna depois do healthcheck passar
        # — pode passar dos 60s padrão do WEBHOOK_TIMEOUT do Zerobyte.
        # Falha aqui só vira warning no Zerobyte (não aborta o backup,
        # que já rodou), então preferível responder logo e deixar o
        # restart em background do que arriscar o webhook estourar o
        # timeout com o stack já parado.
        subprocess.Popen(
            ["systemctl", "--user", "start", *START_ORDER],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._send_json(200, {"ok": True, "action": "start triggered"})

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    load_token()  # falha cedo se o token não existir/não for legível
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"any-sync-bundle webhook listening on 0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
