"""Check the GitHub Models connection without the openai library. Prints no secrets.

Usage (same PowerShell window where the token is set):  python scripts/check_model.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

token = os.environ.get("GITHUB_MODELS_TOKEN")
model = os.environ.get("GITHUB_MODEL", "openai/gpt-4.1-mini")
if not token:
    sys.exit("GITHUB_MODELS_TOKEN is not set in this window")

SHOW = ("server", "via", "x-github-request-id", "content-type", "content-length")


def call(label, url, version, body=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": version}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers)
    print(f"\n--- {label} (api version {version}) ---")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("status:", r.status)
            print({k: r.headers.get(k) for k in SHOW})
            print(r.read().decode("utf-8", "replace")[:400])
    except urllib.error.HTTPError as e:
        print("HTTP error:", e.code, e.reason)
        print({k: e.headers.get(k) for k in SHOW})
        print(e.read().decode("utf-8", "replace")[:400])
    except Exception as e:
        print("connection problem:", type(e).__name__, e)


chat = {"model": model, "messages": [{"role": "user", "content": "Reply with the single word: ready"}]}
call("model catalogue", "https://models.github.ai/catalog/models", "2026-03-10")
call("chat, new api version", "https://models.github.ai/inference/chat/completions", "2026-03-10", chat)
call("chat, old api version", "https://models.github.ai/inference/chat/completions", "2022-11-28", chat)