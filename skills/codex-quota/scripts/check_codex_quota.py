#!/usr/bin/env python3
"""
OpenAI Codex Quota & Plan Status Checker.

Queries the OpenAI Codex headless app-server protocol over stdio (JSON-RPC 2.0)
to inspect real-time rate limit usage, reset countdowns, credits, plan tier,
and model availability without launching the interactive TUI or app.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def query_codex_app_server(timeout: float = 12.0) -> Dict[str, Any]:
    cmd = ["codex", "app-server", "--stdio"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        sys.stderr.write("Error: 'codex' executable not found on PATH.\n")
        sys.exit(1)

    def send(msg: Dict[str, Any]):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    try:
        # 1. Initialize session
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "codex-quota-checker",
                        "version": "1.0.0",
                    }
                },
            }
        )

        init_raw = proc.stdout.readline()
        if not init_raw:
            sys.stderr.write("Error: Codex app-server closed connection during initialize.\n")
            sys.exit(1)

        send({"method": "initialized", "params": {}})

        # 2. Query Account, RateLimits, and Models
        send({"id": 2, "method": "account/read", "params": {}})
        send({"id": 3, "method": "account/rateLimits/read", "params": {}})
        send({"id": 4, "method": "model/list", "params": {}})

        results = {}
        start = time.time()
        while len(results) < 3 and time.time() - start < timeout:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
                req_id = msg.get("id")
                if req_id in (2, 3, 4):
                    results[req_id] = msg.get("result", {})
            except Exception:
                continue

        return {
            "account": results.get(2, {}).get("account", {}),
            "rateLimits": results.get(3, {}),
            "models": results.get(4, {}).get("data", []),
        }
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            pass


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "now (reset passed)"
    mins = int(seconds // 60)
    hours = mins // 60
    rem_mins = mins % 60
    if hours > 24:
        days = hours // 24
        rem_hours = hours % 24
        return f"in {days}d {rem_hours}h"
    elif hours > 0:
        return f"in {hours}h {rem_mins}m"
    else:
        return f"in {rem_mins}m"


def format_window(window: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not window:
        return {"used": "N/A", "remaining": "N/A", "reset": "—", "countdown": "—"}
    used = window.get("usedPercent", 0)
    remaining = max(0, 100 - used)
    reset_ts = window.get("resetsAt")
    duration_mins = window.get("windowDurationMins", 0)

    if reset_ts:
        dt = datetime.fromtimestamp(reset_ts, tz=timezone.utc)
        reset_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        countdown = format_duration(reset_ts - time.time())
    else:
        reset_str = "—"
        countdown = "—"

    return {
        "used": f"{used}%",
        "remaining": f"{remaining}%",
        "remainingVal": remaining,
        "reset": reset_str,
        "countdown": countdown,
        "windowDurationMins": duration_mins,
    }


def format_table(
    account: Dict[str, Any],
    rate_limits: Dict[str, Any],
    models: List[Dict[str, Any]],
    target_model: Optional[str] = None,
) -> str:
    lines = []
    lines.append("=" * 65)
    lines.append("OPENAI CODEX ACCOUNT & RATE LIMIT STATUS")
    lines.append("=" * 65)

    plan = account.get("planType", "unknown").upper()
    email = account.get("email", "N/A")
    lines.append(f"Plan:                 {plan}")
    lines.append(f"Account Email:        {email}")

    rl = rate_limits.get("rateLimits", {})
    credits = rl.get("credits", {})
    balance = credits.get("balance", "0")
    unlimited = credits.get("unlimited", False)
    credits_str = "Unlimited" if unlimited else str(balance)
    lines.append(f"Credits Balance:      {credits_str}")

    reset_credits = rate_limits.get("rateLimitResetCredits", {}).get("availableCount", 0)
    lines.append(f"Reset Credits:        {reset_credits} available")
    lines.append("")

    primary = format_window(rl.get("primary"))
    secondary = format_window(rl.get("secondary"))

    lines.append("-" * 65)
    lines.append("ROLLING RATE LIMIT WINDOWS")
    lines.append("-" * 65)
    primary_label = f"Primary ({primary['windowDurationMins']}m / {primary['windowDurationMins']//60}h)"
    lines.append(f"• {primary_label:<20} : {primary['used']} used ({primary['remaining']} remaining)")
    lines.append(f"  Reset Timestamp     : {primary['reset']} ({primary['countdown']})")

    if secondary.get("windowDurationMins"):
        sec_days = secondary["windowDurationMins"] // 1440
        sec_label = f"Secondary ({sec_days}d window)"
        lines.append(f"• {sec_label:<20} : {secondary['used']} used ({secondary['remaining']} remaining)")
        lines.append(f"  Reset Timestamp     : {secondary['reset']} ({secondary['countdown']})")
    lines.append("-" * 65)

    if target_model:
        lines.append("")
        lines.append(f"TARGET MODEL: {target_model}")
        matched = [
            m
            for m in models
            if target_model.lower() in m.get("id", "").lower()
            or target_model.lower() in m.get("displayName", "").lower()
        ]
        if matched:
            for m in matched:
                efforts = [
                    e.get("reasoningEffort")
                    for e in m.get("supportedReasoningEfforts", [])
                    if "reasoningEffort" in e
                ]
                eff_str = ", ".join(efforts) if efforts else "default"
                lines.append(f"  Model Match         : {m.get('displayName')} (`{m.get('id')}`)")
                lines.append(f"  Reasoning Efforts   : {eff_str}")
                lines.append(f"  Effective Quota     : Governed by {plan} tier ({primary['remaining']} remaining in primary window)")
        else:
            lines.append(f"  Model Match         : Not found in active catalog")
        lines.append("-" * 65)
    elif models:
        lines.append("")
        lines.append("AVAILABLE MODELS (ACTIVE TIER):")
        for m in models:
            lines.append(f"  • {m.get('displayName'):<20} (ID: {m.get('id')})")
        lines.append("-" * 65)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Check OpenAI Codex rate limits and quota without opening the app or interactive CLI."
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=None,
        help="Filter by specific model ID or substring (e.g. 'gpt-6.1-sol', 'sol', 'terra').",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json", "quiet", "raw"],
        default="table",
        help="Output format: table (default), json, quiet, or raw.",
    )
    args = parser.parse_args()

    data = query_codex_app_server()

    if args.format == "raw":
        print(json.dumps(data, indent=2))
        return

    rl = data.get("rateLimits", {}).get("rateLimits", {})
    primary = format_window(rl.get("primary"))
    secondary = format_window(rl.get("secondary"))

    if args.format == "quiet":
        print(primary.get("remaining", "N/A"))
        return

    if args.format == "json":
        output = {
            "account": data.get("account"),
            "planType": rl.get("planType"),
            "primaryWindow": primary,
            "secondaryWindow": secondary,
            "credits": rl.get("credits"),
            "rateLimitResetCredits": data.get("rateLimits", {}).get("rateLimitResetCredits"),
        }
        if args.model:
            matched = [
                m
                for m in data.get("models", [])
                if args.model.lower() in m.get("id", "").lower()
                or args.model.lower() in m.get("displayName", "").lower()
            ]
            output["targetModel"] = args.model
            output["matchedModels"] = matched
        else:
            output["models"] = [
                {"id": m.get("id"), "displayName": m.get("displayName")}
                for m in data.get("models", [])
            ]
        print(json.dumps(output, indent=2))
        return

    print(format_table(data["account"], data["rateLimits"], data["models"], target_model=args.model))


if __name__ == "__main__":
    main()
