#!/usr/bin/env python3
"""Copy the backend's environment from a local .env file onto a Heroku app.

Retyping twenty secrets into a terminal is where deploys go wrong: one truncated
database URL and the app boots against nothing. This reads the file you already
have and hands the values straight to the Heroku CLI.

Values are never printed and never written anywhere. Only variable names appear
in the output, so the transcript stays safe to share.

    python scripts/heroku_config_from_env.py --app buywise-api --dry-run
    python scripts/heroku_config_from_env.py --app buywise-api
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Variables the browser build uses; the API has no use for them. NEXT_PUBLIC_APP_URL
# is the exception: the backend derives its allowed CORS origins from it.
FRONTEND_ONLY = {
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_GOOGLE_CLIENT_ID",
    "NEXT_PUBLIC_GA_MEASUREMENT_ID",
}
# Set from the app's real hostname instead of whatever the local file says.
DERIVED = {"API_PUBLIC_URL", "ENVIRONMENT"}
# Empty locally and meaningless on a single web dyno.
SKIP_IF_EMPTY = {"CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "REDIS_URL", "TRUSTPILOT_API_KEY"}
# Worth a word if they are missing, because a feature quietly stops working.
EXPECTED = {
    "DATABASE_URL": "the database: the app cannot start without it",
    "SECRET_KEY": "sessions: must match the old host or everyone is signed out",
    "SERPAPI_API_KEY": "live search results",
    "GEMINI_API_KEY": "AI answers",
    "OPENAI_API_KEY": "the Groq fallback for when Gemini caps out",
    "OPENAI_BASE_URL": "the Groq endpoint; without it this points at OpenAI",
    "GOOGLE_CLIENT_ID": "sign in with Google",
    "CRON_SECRET": "scheduled price refreshes",
}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key.replace("_", "").isalnum():
            continue
        value = value.split(" #")[0].strip().strip("'\"")
        values[key] = value
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, help="Heroku app name")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).resolve().parents[2] / ".env",
        help="Local .env to read (default: repository root .env)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List what would be set, then stop")
    args = parser.parse_args()

    if shutil.which("heroku") is None and not args.dry_run:
        print("The Heroku CLI is not installed. brew install heroku/brew/heroku", file=sys.stderr)
        return 1
    if not args.env_file.is_file():
        print(f"No such file: {args.env_file}", file=sys.stderr)
        return 1

    values = parse_env(args.env_file)

    web_url = f"https://{args.app}.herokuapp.com"
    if not args.dry_run:
        try:
            info = json.loads(
                subprocess.run(
                    ["heroku", "apps:info", "-a", args.app, "--json"],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )
            web_url = (info.get("app") or {}).get("web_url", web_url).rstrip("/")
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
            print(f"Could not read the app's URL; assuming {web_url}", file=sys.stderr)

    outgoing: dict[str, str] = {}
    for key, value in values.items():
        if key in FRONTEND_ONLY or key in DERIVED:
            continue
        if key in SKIP_IF_EMPTY and not value:
            continue
        if not value:
            continue
        outgoing[key] = value
    outgoing["ENVIRONMENT"] = "production"
    outgoing["API_PUBLIC_URL"] = web_url

    print(f"App:      {args.app}")
    print(f"From:     {args.env_file}")
    print(f"Setting:  {len(outgoing)} variables\n")
    for key in sorted(outgoing):
        note = "  <- derived" if key in DERIVED else ""
        print(f"  {key}{note}")

    missing = [k for k in EXPECTED if not outgoing.get(k)]
    if missing:
        print("\nNot in the file, so not set:")
        for key in missing:
            print(f"  {key:22} {EXPECTED[key]}")
        print("\nSet those on Heroku yourself, or add them to the file and re-run.")

    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0

    pairs = [f"{k}={v}" for k, v in outgoing.items()]
    result = subprocess.run(
        ["heroku", "config:set", "-a", args.app, *pairs],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Heroku echoes the config back on success; on failure print only its
        # error stream, which does not contain the values we sent.
        print(result.stderr.strip()[:500], file=sys.stderr)
        return result.returncode
    print(f"\nSet {len(outgoing)} variables on {args.app}.")
    print("Values were not printed. Check them with: heroku config -a " + args.app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
