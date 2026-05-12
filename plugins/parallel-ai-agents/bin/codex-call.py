#!/usr/bin/env python3
"""
codex-call.py — direct HTTP wrapper for chatgpt.com/backend-api

Replaces `codex exec --full-auto -o output "prompt"` with a clean HTTP call
that bypasses the codex CLI subprocess (which can hang on stdin/stdout pipes).

Usage:
  codex-call.py --output FILE [--model gpt-5.5] [--effort xhigh]
                [--service-tier fast] [--max-time 600]
                [--prompt-file FILE | PROMPT]

Auth: reads ~/.codex/auth.json, auto-refreshes access_token if within
5 min of expiry. Refresh uses a file lock to prevent concurrent races.
"""

import argparse
import base64
import fcntl
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AUTH_FILE = Path.home() / ".codex" / "auth.json"
LOCK_FILE = Path.home() / ".codex" / ".token-refresh.lock"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
REFRESH_THRESHOLD_SEC = 300


def jwt_exp(token: str) -> int:
    parts = token.split(".")
    if len(parts) < 2:
        return 0
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload).decode()
        return int(json.loads(decoded).get("exp", 0))
    except Exception:
        return 0


def load_auth() -> dict:
    with open(AUTH_FILE) as f:
        return json.load(f)


def save_auth(auth: dict) -> None:
    tmp = AUTH_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(auth, f, indent=2)
    os.chmod(tmp, 0o600)
    tmp.replace(AUTH_FILE)


def refresh_if_needed(auth: dict) -> dict:
    access = auth["tokens"]["access_token"]
    if jwt_exp(access) - int(time.time()) > REFRESH_THRESHOLD_SEC:
        return auth

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        auth = load_auth()
        if jwt_exp(auth["tokens"]["access_token"]) - int(time.time()) > REFRESH_THRESHOLD_SEC:
            return auth

        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": auth["tokens"]["refresh_token"],
            "client_id": CLIENT_ID,
        }).encode()
        req = urllib.request.Request(
            TOKEN_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            sys.stderr.write(f"[codex-call] refresh failed: {e.code} {e.read().decode()[:200]}\n")
            raise

        auth["tokens"]["access_token"] = result["access_token"]
        auth["tokens"]["refresh_token"] = result.get("refresh_token", auth["tokens"]["refresh_token"])
        if "id_token" in result:
            auth["tokens"]["id_token"] = result["id_token"]
        auth["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        save_auth(auth)
        sys.stderr.write("[codex-call] token refreshed\n")
        return auth


def stream_codex(prompt: str, output_file: str, model: str, effort: str,
                 service_tier: str, max_time: int, instructions: str | None) -> None:
    auth = refresh_if_needed(load_auth())
    access = auth["tokens"]["access_token"]
    account_id = auth["tokens"].get("account_id", "")

    body: dict = {
        "model": model,
        "store": False,
        "stream": True,
        "instructions": instructions or "You are a careful, rigorous reviewer. Respond in the user's language.",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "text": {"verbosity": "medium"},
        "include": ["reasoning.encrypted_content"],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "reasoning": {"effort": effort, "summary": "auto"},
    }
    if service_tier:
        body["service_tier"] = service_tier

    req = urllib.request.Request(
        CODEX_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "responses=experimental",
            "originator": "codex_cli_rs",
            "chatgpt-account-id": account_id,
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    accumulated: list[str] = []
    event_lines: list[str] = []

    def flush_event() -> None:
        if not event_lines:
            return
        data_payload = "".join(
            line[5:].lstrip() for line in event_lines if line.startswith("data:")
        )
        event_lines.clear()
        if not data_payload or data_payload == "[DONE]":
            return
        try:
            evt = json.loads(data_payload)
        except json.JSONDecodeError:
            return
        t = evt.get("type", "")
        if t == "response.output_text.delta":
            accumulated.append(evt.get("delta", ""))
        elif t == "response.reasoning_text.delta":
            pass  # ignore reasoning summary
        elif t in ("error", "response.failed"):
            msg = (evt.get("message")
                   or evt.get("response", {}).get("error", {}).get("message")
                   or json.dumps(evt)[:200])
            raise RuntimeError(f"Codex stream error: {msg}")

    try:
        with urllib.request.urlopen(req, timeout=max_time) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    flush_event()
                else:
                    event_lines.append(line)
            flush_event()
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[codex-call] HTTP {e.code}: {e.read().decode()[:500]}\n")
        raise

    text = "".join(accumulated)
    Path(output_file).write_text(text)
    sys.stderr.write(f"[codex-call] wrote {len(text)} chars to {output_file}\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output", "-o", required=True, help="output file path")
    p.add_argument("--model", default="gpt-5.5")
    p.add_argument("--effort", default="xhigh", choices=["minimal", "low", "medium", "high", "xhigh"])
    p.add_argument("--service-tier", default="fast", choices=["", "default", "fast", "priority"])
    p.add_argument("--max-time", type=int, default=600, help="hard timeout in seconds")
    p.add_argument("--instructions", help="optional system prompt")
    p.add_argument("--prompt-file", help="read prompt from file (else use positional)")
    p.add_argument("prompt", nargs="?", default=None)
    args = p.parse_args()

    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text()
    elif args.prompt:
        prompt = args.prompt
    else:
        prompt = sys.stdin.read()
    if not prompt.strip():
        sys.exit("error: empty prompt")

    stream_codex(
        prompt=prompt,
        output_file=args.output,
        model=args.model,
        effort=args.effort,
        service_tier=args.service_tier,
        max_time=args.max_time,
        instructions=args.instructions,
    )


if __name__ == "__main__":
    main()
