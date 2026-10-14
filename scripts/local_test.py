"""Start the isolated manual stack, configure free models, and exercise a virtual key."""

import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".env.local-test"
PROXY = "http://127.0.0.1:4000"
PORTAL = "http://127.0.0.1:8000"
MASTER = "sk-litegate-integration-master"  # Disposable Compose stack's test credential.


def call(base, path, *, key=None, payload=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(base + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    value = {
        "password": secrets.token_urlsafe(18),
        "jwt": secrets.token_urlsafe(48),
        "management": secrets.token_urlsafe(32),
    }
    with os.fdopen(
        os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as output:
        json.dump(value, output, indent=2)
    return value


def launch(arguments, directory, environment, log_name):
    logs = ROOT / ".env.local-test-logs"
    logs.mkdir(exist_ok=True)
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    with (logs / log_name).open("a") as output:
        process = subprocess.Popen(
            arguments,
            cwd=directory,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            **options,
        )
    print(f"Started PID {process.pid}; log: {logs / log_name}")


def ready(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=2) as response:
            response.read(1)
        return True
    except (urllib.error.URLError, TimeoutError):
        return False


def wait_ready(base, path):
    for _ in range(120):
        if ready(base, path):
            return
        time.sleep(1)
    raise RuntimeError(
        f"Service not ready: {base}; inspect .env.local-test-logs/manual-*.log"
    )


def start():
    environment = {**os.environ, "LITELLM_INTEGRATION_PORT": "127.0.0.1:4000"}
    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            "litegate-local-test",
            "-f",
            str(ROOT / "deploy/docker-compose/docker-compose.integration.yml"),
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
        ],
        env=environment,
        check=True,
    )
    access = state()
    environment.update(
        {
            "LITELLM_URL": PROXY,
            "LITELLM_MASTER_KEY": MASTER,
            "JWT_SECRET": access["jwt"],
            "MANAGEMENT_API_KEY": access["management"],
            "LOCAL_AUTH_USERNAME": "admin",
            "LOCAL_AUTH_PASSWORD": access["password"],
            "LOCAL_USERS_DB_PATH": "data/litegate-manual-test.db",
            "SAVE_API_KEYS_IN_DB": "true",
            "ROOT_URL": "http://localhost:5189",
            "CORS_ORIGINS": "http://localhost:5189,http://127.0.0.1:5189",
            "VITE_DEMO_MODE": "false",
        }
    )
    config = ROOT / "backend/config.yaml"
    if not config.exists():
        config.write_text(
            (ROOT / "deploy/docker-compose/config.local-test.yaml").read_text()
        )
    if ready(PORTAL, "/api/health/ready"):
        raise RuntimeError(
            "Port 8000 already serves an application. Stop it before starting this isolated setup."
        )
    launch(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--reload",
            "--reload-include",
            "config.yaml",
        ],
        ROOT / "backend",
        environment,
        "manual-backend.log",
    )
    wait_ready(PORTAL, "/api/health/ready")
    if not ready("http://127.0.0.1:5189", "/"):
        launch(
            [
                "node",
                "node_modules/vite/bin/vite.js",
                "--host",
                "127.0.0.1",
                "--port",
                "5189",
                "--strictPort",
            ],
            ROOT / "frontend",
            environment,
            "manual-frontend.log",
        )
    wait_ready("http://127.0.0.1:5189", "/api/health/ready")
    existing = call(PORTAL, "/api/v1/users", key=access["management"])
    names = {user["username"] for user in existing}
    for name in ("alice", "bob", "carol"):
        if name not in names:
            call(
                PORTAL,
                "/api/v1/users",
                key=access["management"],
                payload={
                    "username": name,
                    "email": f"{name}@example.invalid",
                    "password": access["password"],
                    "role": "user",
                },
            )
    print("\nLiteGate: http://localhost:5189 | LiteLLM: http://localhost:4000/ui")
    print(
        f"LiteGate accounts: admin, alice, bob, carol | password: {access['password']}"
    )
    print(
        f"Hierarchy: {config} (saving reloads the backend; reconciliation runs every 60 seconds)"
    )
    print("Next: python scripts/local_test.py providers")


def providers():
    provider_key = os.environ.get("OPENROUTER_API_KEY") or getpass.getpass(
        "OpenRouter API key (hidden): "
    )
    if not provider_key:
        raise ValueError("An OpenRouter API key is required")
    catalog = call("https://openrouter.ai", "/api/v1/models")["data"]
    free = sorted(
        model["id"]
        for model in catalog
        if model["id"].endswith(":free")
        and all(
            model.get("pricing", {}).get(field) in ("0", "0.0", 0)
            for field in ("prompt", "completion")
        )
    )
    selected = [("free-router", "openrouter/free")]
    seen = set()
    for model in free:
        author = model.split("/")[0]
        if author not in seen:
            seen.add(author)
            selected.append((f"free-{len(selected)}", model))
        if len(selected) == 3:
            break
    existing = call(PROXY, "/model/info", key=MASTER).get("data", [])
    names = {model["model_name"] for model in existing}
    for alias, model in selected:
        if alias in names:
            print(f"{alias} already configured; left unchanged")
            continue
        call(
            PROXY,
            "/model/new",
            key=MASTER,
            payload={
                "model_name": alias,
                "litellm_params": {
                    "model": f"openrouter/{model}",
                    "api_key": provider_key,
                },
                "model_info": {
                    "mode": "chat",
                    "input_cost_per_token": 0,
                    "output_cost_per_token": 0,
                },
            },
        )
        print(f"Configured {alias}: {model}")
    print(
        "Use a user key created in LiteGate: python scripts/local_test.py request --model free-router"
    )
    print(
        "Free models have provider quotas and zero token spend; they do not exercise dollar-budget exhaustion."
    )


def request(args):
    key = os.environ.get("LITEGATE_TEST_KEY") or getpass.getpass(
        "User virtual key from LiteGate (hidden): "
    )
    if not key:
        raise ValueError("A user virtual key is required")
    if key == MASTER:
        raise ValueError("Use a user's virtual key, not the LiteLLM master key")
    for index in range(args.count):
        try:
            result = call(
                PROXY,
                "/v1/chat/completions",
                key=key,
                payload={
                    "model": args.model,
                    "messages": [{"role": "user", "content": args.prompt}],
                    "max_tokens": 64,
                },
            )
        except urllib.error.HTTPError as exc:
            print(
                f"Request {index + 1}: HTTP {exc.code}; inspect the user's key/team policy and provider quota."
            )
            raise SystemExit(1) from None
        print(f"Request {index + 1}: {result['choices'][0]['message'].get('content')}")
        print("Usage:", result.get("usage", {}))
        if index + 1 < args.count:
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "start",
        help="Start disposable LiteLLM plus a real LiteGate backend and local test accounts",
    )
    commands.add_parser(
        "providers",
        help="Register three free OpenRouter model aliases using a locally supplied API key",
    )
    send = commands.add_parser(
        "request", help="Send real model requests using a user virtual key"
    )
    send.add_argument("--model", default="free-router")
    send.add_argument(
        "--prompt",
        default="Reply with one short sentence confirming the request worked.",
    )
    send.add_argument("--count", type=int, choices=range(1, 21), default=1)
    args = parser.parse_args()
    try:
        {"start": start, "providers": providers, "request": lambda: request(args)}[
            args.command
        ]()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except (urllib.error.URLError, ValueError, subprocess.CalledProcessError) as exc:
        print(
            f"Local test failed: {type(exc).__name__}. Check service logs, credentials, and connectivity.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
