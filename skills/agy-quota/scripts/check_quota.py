#!/usr/bin/env python3
"""
Antigravity Quota & Plan Status Checker.

Queries the local Antigravity Language Server (127.0.0.1) over HTTP Connect/gRPC
to inspect real-time rate limit quotas, credit pools (prompt/flow), plan tier,
and per-model availability.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def get_connection_info(
    addr_override: Optional[str] = None, csrf_override: Optional[str] = None
) -> Tuple[str, str]:
    if addr_override:
        os.environ["ANTIGRAVITY_LS_ADDRESS"] = addr_override
    if csrf_override:
        os.environ["ANTIGRAVITY_CSRF_TOKEN"] = csrf_override
    addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS") or ""
    csrf = os.environ.get("ANTIGRAVITY_CSRF_TOKEN") or ""
    return addr, csrf


def run_via_agy(args: argparse.Namespace) -> int:
    """Run this script inside an `agy -p` session so ANTIGRAVITY_LS_ADDRESS/CSRF_TOKEN are populated."""
    agy_bin = shutil.which("agy")
    if not agy_bin:
        sys.stderr.write("Error: 'agy' binary not found on PATH for --via-agy.\n")
        return 1
    forward_args: List[str] = [sys.executable, str(Path(__file__).resolve())]
    if args.model:
        forward_args.extend(["-m", args.model])
    if args.format:
        forward_args.extend(["-f", args.format])
    if args.credits_only:
        forward_args.append("--credits-only")
    if args.models_only:
        forward_args.append("--models-only")
    if args.all:
        forward_args.append("--all")
    shell_cmd = " ".join(shlex.quote(a) for a in forward_args)
    prompt = f"Run this exact command and print ONLY its raw stdout with no extra commentary: {shell_cmd}"
    proc = subprocess.run(
        [
            agy_bin,
            f"-p={prompt}",
            "--disable-slash-commands",
            "--dangerously-skip-permissions",
            "--print-timeout",
            "45s",
        ],
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr and proc.returncode != 0:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def fetch_user_status(addr: str, csrf: str, timeout: float = 5.0) -> Dict[str, Any]:
    url = f"http://{addr}/exa.language_server_pb.LanguageServerService/GetUserStatus"
    headers = {
        "Content-Type": "application/json",
        "x-codeium-csrf-token": csrf,
    }
    req = urllib.request.Request(url, data=b"{}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.URLError as e:
        sys.stderr.write(
            f"Error connecting to Antigravity language server at {addr}: {e.reason}\n"
            "Make sure Antigravity (agy / Antigravity IDE) is running and "
            "ANTIGRAVITY_LS_ADDRESS and ANTIGRAVITY_CSRF_TOKEN are set.\n"
        )
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Unexpected error querying language server: {e}\n")
        sys.exit(1)


def parse_models(
    raw_status: Dict[str, Any], include_all: bool = False
) -> List[Dict[str, Any]]:
    user_status = raw_status.get("userStatus", {})
    configs = (
        user_status.get("cascadeModelConfigData", {}).get("clientModelConfigs", [])
    )
    models = []
    for c in configs:
        quota = c.get("quotaInfo", {})
        rem = quota.get("remainingFraction")
        reset = quota.get("resetTime")
        has_quota = rem is not None or reset is not None

        if not has_quota and not include_all:
            continue

        models.append(
            {
                "label": c.get("label", "Unknown"),
                "modelId": c.get("modelId", "unknown"),
                "remainingFraction": rem,
                "resetTime": reset,
                "supportsImages": c.get("supportsImages", False),
                "allowedTiers": c.get("allowedTiers", []),
                "hasQuotaLimit": has_quota,
            }
        )
    return models


def find_matching_models(
    models: List[Dict[str, Any]], query: str
) -> List[Dict[str, Any]]:
    query_lower = query.strip().lower()
    # Exact match first
    exact = [
        m
        for m in models
        if m["modelId"].lower() == query_lower or m["label"].lower() == query_lower
    ]
    if exact:
        return exact

    # Substring match
    matches = [
        m
        for m in models
        if query_lower in m["modelId"].lower() or query_lower in m["label"].lower()
    ]
    return matches


def format_table(
    plan_info: Dict[str, Any],
    models: List[Dict[str, Any]],
    show_plan: bool = True,
    show_models: bool = True,
) -> str:
    lines = []

    if show_plan:
        lines.append("=" * 60)
        lines.append("ANTIGRAVITY ACCOUNT & PLAN STATUS")
        lines.append("=" * 60)
        plan_name = plan_info.get("planInfo", {}).get("planName", "N/A")
        tier = plan_info.get("planInfo", {}).get("teamsTier", "N/A")
        lines.append(f"Plan:                 {plan_name} ({tier})")

        avail_prompt = plan_info.get("availablePromptCredits")
        monthly_prompt = plan_info.get("planInfo", {}).get("monthlyPromptCredits")
        avail_flow = plan_info.get("availableFlowCredits")
        monthly_flow = plan_info.get("planInfo", {}).get("monthlyFlowCredits")

        prompt_str = f"{avail_prompt:,}" if isinstance(avail_prompt, (int, float)) else str(avail_prompt)
        monthly_prompt_str = f"{monthly_prompt:,}" if isinstance(monthly_prompt, (int, float)) else str(monthly_prompt)
        flow_str = f"{avail_flow:,}" if isinstance(avail_flow, (int, float)) else str(avail_flow)
        monthly_flow_str = f"{monthly_flow:,}" if isinstance(monthly_flow, (int, float)) else str(monthly_flow)

        lines.append(f"Prompt Credits:       {prompt_str} / {monthly_prompt_str} (monthly)")
        lines.append(f"Flow Credits:         {flow_str} / {monthly_flow_str} (monthly)")
        lines.append("")

    if show_models:
        lines.append("-" * 75)
        lines.append(f"{'MODEL':<28} {'MODEL ID':<24} {'REMAINING':<11} {'RESET TIME'}")
        lines.append("-" * 75)

        for m in models:
            label = m["label"]
            if len(label) > 26:
                label = label[:23] + "..."
            mid = m["modelId"]
            if len(mid) > 22:
                mid = mid[:19] + "..."

            rem = m["remainingFraction"]
            if rem is not None:
                rem_str = f"{rem * 100:>5.1f}%"
            else:
                rem_str = "  N/A  "

            reset = m["resetTime"] or "—"
            lines.append(f"{label:<28} {mid:<24} {rem_str:<11} {reset}")

        lines.append("-" * 75)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Query Antigravity local language server for quota usage and plan status."
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=None,
        help="Filter by specific model ID or label substring (e.g., 'flash', 'claude-sonnet-4-6', 'gpt-oss').",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json", "raw", "quiet"],
        default="table",
        help="Output format: table (default), json, raw, or quiet (raw fraction/number only).",
    )
    parser.add_argument(
        "--credits-only",
        action="store_true",
        help="Display only available prompt and flow credits.",
    )
    parser.add_argument(
        "--models-only",
        action="store_true",
        help="Display only model quotas, omitting account plan details.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include disabled models and models without active quota limits.",
    )
    parser.add_argument(
        "--addr",
        type=str,
        default=None,
        help="Language server address (sets ANTIGRAVITY_LS_ADDRESS).",
    )
    parser.add_argument(
        "--csrf",
        type=str,
        default=None,
        help="Language server CSRF token (sets ANTIGRAVITY_CSRF_TOKEN).",
    )
    parser.add_argument(
        "--via-agy",
        action="store_true",
        help="When running outside an Antigravity session, invoke `agy -p` so LS env vars are populated.",
    )

    args = parser.parse_args()

    addr, csrf = get_connection_info(args.addr, args.csrf)
    if not addr:
        if args.via_agy:
            sys.exit(run_via_agy(args))
        sys.stderr.write(
            "Error: ANTIGRAVITY_LS_ADDRESS is not set (not inside an active Antigravity session).\n"
            "Set ANTIGRAVITY_LS_ADDRESS and ANTIGRAVITY_CSRF_TOKEN, pass --addr/--csrf, or pass --via-agy.\n"
        )
        sys.exit(1)
    raw = fetch_user_status(addr, csrf)

    if args.format == "raw":
        print(json.dumps(raw, indent=2))
        return

    user_status = raw.get("userStatus", {})
    plan_info = user_status.get("planStatus", {})
    models = parse_models(raw, include_all=args.all)

    # Filter by model if requested
    if args.model:
        matched = find_matching_models(models, args.model)
        if not matched:
            sys.stderr.write(f"No model found matching query: '{args.model}'\n")
            sys.stderr.write("Available models:\n")
            for m in models:
                sys.stderr.write(f"  - {m['label']} ({m['modelId']})\n")
            sys.exit(1)
        models = matched

    if args.format == "json":
        result = {
            "address": addr,
            "planStatus": plan_info,
            "models": models,
        }
        if args.credits_only:
            result = plan_info
        elif args.models_only or args.model:
            result = models if len(models) > 1 else models[0]
        print(json.dumps(result, indent=2))
        return

    if args.format == "quiet":
        if args.model:
            for m in models:
                rem = m.get("remainingFraction")
                if rem is not None:
                    print(f"{rem * 100:.2f}%")
                else:
                    print("N/A")
            return
        elif args.credits_only:
            prompt = plan_info.get("availablePromptCredits", 0)
            flow = plan_info.get("availableFlowCredits", 0)
            print(f"prompt={prompt} flow={flow}")
            return

    # Table format
    show_plan = not args.models_only and not args.model
    show_models = not args.credits_only
    print(format_table(plan_info, models, show_plan=show_plan, show_models=show_models))


if __name__ == "__main__":
    main()
