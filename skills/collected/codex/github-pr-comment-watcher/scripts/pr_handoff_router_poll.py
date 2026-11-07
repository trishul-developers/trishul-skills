#!/usr/bin/env python3
"""Generic local PR handoff poller driven by a per-Issue/PR JSON config.

The OS scheduler invokes this script. Idle comment polls use no model; only new
handoffs and exceptions wake a Codex chat.
"""

import argparse
import hashlib
import json
import msvcrt
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = REGISTRY = STATE = PENDING = ALERT = EVENTS = ACK_DIR = CONFIG_PATH = None
LOCK = LOG = ERROR_STATE = REVISIONS = None
BOOTSTRAP_ROUTER_THREAD = ORCHESTRATOR_THREAD = None
REPO_OWNER = REPO_NAME = PR_NUMBER = ISSUE_NUMBER = TRUSTED_AUTHORS = None
EXTERNAL_ROLES = set()
ROUTING_ENABLED = True
RESULT_TIMEOUT_SECONDS = 4 * 3600
ALIASES = {
    "COORDINATOR": "COORDINATOR",
    "IMPLEMENTOR-1": "IMPLEMENTOR-CLOUD",
    "IMPLEMENTOR": "IMPLEMENTOR-CLOUD",
    "IMPLEMENTOR-CLOUD": "IMPLEMENTOR-CLOUD",
    "IMPLEMENTOR-LOCAL": "IMPLEMENTOR-LOCAL",
    "REVIEWER-1A": "REVIEWER-A",
    "REVIEWER-A": "REVIEWER-A",
    "REVIEWER-1B": "REVIEWER-B",
    "REVIEWER-B": "REVIEWER-B",
}
HEADER = re.compile(r"^\[([A-Z][A-Z0-9-]*)\](?:\s|$)")
FIELD = re.compile(r"^([A-Z][A-Z0-9_]*):[ \t]*(.*?)[ \t]*$", re.MULTILINE)
HANDOFF = re.compile(r"ISSUE[0-9]+-[0-9]+")
ROUTER_ID = re.compile(r"^ROUTER_THREAD:\s*([0-9a-fA-F-]{36})\s*$", re.MULTILINE)
QUERY = """query($owner:String!,$name:String!,$number:Int!,$before:String){
  repository(owner:$owner,name:$name){pullRequest(number:$number){
    comments(last:100,before:$before){pageInfo{hasPreviousPage startCursor}
      edges{node{databaseId createdAt body author{login}}}}
  }}
}"""


def configure(path):
    global ROOT, REGISTRY, STATE, PENDING, ALERT, EVENTS, ACK_DIR, CONFIG_PATH
    global LOCK, LOG, ERROR_STATE, REVISIONS
    global BOOTSTRAP_ROUTER_THREAD, ORCHESTRATOR_THREAD
    global REPO_OWNER, REPO_NAME, PR_NUMBER, ISSUE_NUMBER, TRUSTED_AUTHORS, EXTERNAL_ROLES
    global RESULT_TIMEOUT_SECONDS, ROUTING_ENABLED
    CONFIG_PATH = Path(path).resolve()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    ROOT = Path(config["workspace"]).resolve()
    owner, name = config["repository"].split("/", 1)
    REPO_OWNER, REPO_NAME = owner, name
    TRUSTED_AUTHORS = set(config.get("trusted_authors", [owner]))
    EXTERNAL_ROLES = set(config.get("external_roles", []))
    ROUTING_ENABLED = bool(config.get("routing_enabled", True))
    ISSUE_NUMBER, PR_NUMBER = int(config["issue"]), int(config["pr"])
    REGISTRY = Path(config.get("registry", ROOT / ".agents/state/REGISTRY.md"))
    prefix = ROOT / "Logs" / config.get("state_prefix", f"pr{PR_NUMBER}_comment_router")
    STATE = prefix.with_suffix(".cursor")
    PENDING = prefix.with_suffix(".pending.json")
    ALERT = prefix.with_suffix(".alert.json")
    EVENTS = prefix.with_suffix(".events.json")
    REVISIONS = prefix.with_suffix(".revisions.json")
    ACK_DIR = prefix.with_suffix(".ack")
    LOCK = prefix.with_suffix(".lock")
    LOG = ROOT / "Logs" / f"pr{PR_NUMBER}_comment_router_poll.log"
    ERROR_STATE = ROOT / "Logs" / f"pr{PR_NUMBER}_router_errors.json"
    BOOTSTRAP_ROUTER_THREAD = config.get("bootstrap_router_thread")
    ORCHESTRATOR_THREAD = config["orchestrator_thread"]
    RESULT_TIMEOUT_SECONDS = int(config.get("result_timeout_hours", 4) * 3600)
    if not ROOT.is_dir() or not REGISTRY.is_file():
        raise ValueError("workspace and registry must exist")
    if not BOOTSTRAP_ROUTER_THREAD and not ROUTER_ID.search(REGISTRY.read_text(encoding="utf-8")):
        raise ValueError("router UUID is missing from config and registry")


def log(message):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as out:
        out.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {message}\n")


def atomic_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".pr28-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(value)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def executable(name):
    if name == "gh":
        path = Path(r"C:\Program Files\GitHub CLI\gh.exe")
        if path.is_file():
            return str(path)
    else:
        candidates = list((Path.home() / "AppData/Local/OpenAI/Codex/bin").glob("*/codex.exe"))
        if candidates:
            return str(max(candidates, key=lambda p: p.stat().st_mtime))
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"{name} executable is unavailable")
    return found


def command(argv):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=45,
                            creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    if result.returncode:
        raise RuntimeError(f"{Path(argv[0]).name} exited {result.returncode}: {result.stderr.strip()[:400]}")
    return result.stdout


def unseen_comments(cursor):
    pages = []
    before = None
    while True:
        args = [executable("gh"), "api", "graphql", "-f", f"query={QUERY}",
                "-f", f"owner={REPO_OWNER}", "-f", f"name={REPO_NAME}",
                "-F", f"number={PR_NUMBER}"]
        if before is not None:
            args += ["-f", f"before={before}"]
        data = json.loads(command(args))
        if data.get("errors"):
            raise RuntimeError(f"GraphQL error: {str(data['errors'])[:400]}")
        connection = data["data"]["repository"]["pullRequest"]["comments"]
        nodes = [edge["node"] for edge in connection["edges"]]
        if not nodes:
            break
        pages.append(nodes)
        if int(nodes[0]["databaseId"]) <= cursor or not connection["pageInfo"]["hasPreviousPage"]:
            break
        before = connection["pageInfo"]["startCursor"]
    unseen = [node for page in reversed(pages) for node in page
              if int(node["databaseId"]) > cursor]
    return unseen, pages[0] if pages else []


def route(comment):
    if comment.get("author", {}).get("login") not in TRUSTED_AUTHORS:
        return None
    body = comment.get("body") or ""
    header = HEADER.match(body.lstrip("\ufeff"))
    if not header or header.group(1) not in ALIASES:
        return None
    fields = {key: value.strip().strip("`") for key, value in FIELD.findall(body)}
    # Implementor/reviewer result comments identify the consumed assignment
    # with CONSUMES and route onward with NEXT_OWNER. Accept that field so
    # downstream Coordinator handoffs are not skipped as non-routing comments.
    handoff = (fields.get("HANDOFF") or fields.get("ASSIGNMENT_ID") or
               fields.get("CONSUMES"))
    if not handoff:
        match = HANDOFF.search(body.splitlines()[0])
        handoff = match.group() if match else None
    if (not handoff or not HANDOFF.fullmatch(handoff)
            or not handoff.startswith(f"ISSUE{ISSUE_NUMBER}-")):
        return None
    target = fields.get("ASSIGNED_TO") if header.group(1) == "COORDINATOR" else fields.get("NEXT_OWNER")
    canonical_target = ALIASES.get(target)
    return (canonical_target, handoff) if canonical_target else None


def read_cursor():
    if not STATE.exists():
        return 0
    return int(STATE.read_text(encoding="utf-8").strip())


def read_pending():
    if not PENDING.exists():
        return {}
    return json.loads(PENDING.read_text(encoding="utf-8"))


def read_alert():
    if not ALERT.exists():
        return {}
    return json.loads(ALERT.read_text(encoding="utf-8"))


def read_events():
    if not EVENTS.exists():
        return {}
    return json.loads(EVENTS.read_text(encoding="utf-8"))


def save_events(events):
    atomic_text(EVENTS, json.dumps(events, ensure_ascii=False, indent=2) + "\n")


def body_revision(comment):
    return hashlib.sha256((comment.get("body") or "").encode("utf-8")).hexdigest()[:16]


def fields_for(comment):
    return {key: value.strip().strip("`") for key, value in
            FIELD.findall(comment.get("body") or "")}


def consumes_handoff(comment, role, handoff):
    if comment.get("author", {}).get("login") not in TRUSTED_AUTHORS:
        return False
    header = HEADER.match((comment.get("body") or "").lstrip("\ufeff"))
    if not header or ALIASES.get(header.group(1)) != role:
        return False
    fields = fields_for(comment)
    if any(HANDOFF.search(fields.get(key, "")) and
           HANDOFF.search(fields[key]).group() == handoff
           for key in ("CONSUMES", "ASSIGNMENT_ID", "HANDOFF")):
        return True
    # Coordinator owns one monotonic handoff stream. A later Coordinator
    # handoff supersedes an older Coordinator input even when a role result
    # used a mismatched label in its CONSUMES field.
    if role == "COORDINATOR":
        next_id = HANDOFF.fullmatch(fields.get("HANDOFF", ""))
        current_id = HANDOFF.fullmatch(handoff)
        if next_id and current_id:
            next_issue, next_number = next_id.group().split("-", 1)
            current_issue, current_number = current_id.group().split("-", 1)
            return next_issue == current_issue and int(next_number) > int(current_number)
    return False


def registry_role_uuid(role):
    rows = REGISTRY.read_text(encoding="utf-8").split("## Replacement history", 1)[0]
    for line in rows.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 6 and cells[0] == f"#{ISSUE_NUMBER}" and cells[1] == f"#{PR_NUMBER}" and cells[2] == role:
            return cells[4], cells[5]
    return "UNKNOWN", "MISSING"


def prepare_event(event_id):
    events = read_events()
    event = events.get(event_id)
    if not event:
        return {"status": "BLOCKED", "reason": "unknown event"}
    ack_path = ACK_DIR / f"{event_id}.json"
    ack = read_json(ack_path)
    if ack.get("status") in ("DELIVERED", "SKIPPED"):
        return {"status": ack["status"], "reason": "already acknowledged"}
    if event.get("role") in EXTERNAL_ROLES:
        return {"status": "EXTERNAL"}
    comment_id = int(event.get("comment_id", event_id.split("-", 1)[0]))
    try:
        later, _ = unseen_comments(comment_id - 1)
    except Exception as exc:
        return {"status": "BLOCKED", "reason":
                f"GitHub read failed: {type(exc).__name__}: {str(exc)[:200]}"}
    source = next((item for item in later if int(item["databaseId"]) == comment_id), None)
    if source is None:
        return {"status": "BLOCKED", "reason": "source comment unavailable"}
    if ((event.get("revision") and body_revision(source) != event["revision"]) or
            route(source) != (event.get("role"), event.get("handoff"))):
        atomic_text(ack_path, json.dumps({"status": "SKIPPED", "reason": "handoff edited or withdrawn"}))
        return {"status": "SKIPPED", "reason": "handoff edited or withdrawn"}
    if any(consumes_handoff(item, event["role"], event["handoff"])
           for item in later if int(item["databaseId"]) > comment_id):
        atomic_text(ack_path, json.dumps({"status": "SKIPPED", "reason": "later target-role result exists"}))
        return {"status": "SKIPPED", "reason": "later target-role result exists"}
    target_uuid, chat_status = registry_role_uuid(event["role"])
    if target_uuid == "UNKNOWN" or chat_status in ("MISSING", "BLOCKED", "RETIRED", "REPLACED"):
        return {"status": "BLOCKED", "reason": "target chat unavailable", "role": event["role"]}
    return {"status": "READY", "target_uuid": target_uuid, "role": event["role"],
            "ack_path": str(ack_path)}


def router_thread():
    if REGISTRY.exists():
        match = ROUTER_ID.search(REGISTRY.read_text(encoding="utf-8"))
        if match:
            return match.group(1)
    if BOOTSTRAP_ROUTER_THREAD:
        return BOOTSTRAP_ROUTER_THREAD
    raise RuntimeError("ROUTER_THREAD is missing from the registry")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def poll(dry_run):
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
        try:
            cursor = read_cursor()
            comments, recent = unseen_comments(cursor)
            events = read_events()
            revisions = read_json(REVISIONS)
            # Existing comment IDs can be edited in place. Baseline recent comments
            # once, then treat later body changes as independent routing revisions.
            for comment in recent:
                comment_id = int(comment["databaseId"])
                if comment_id > cursor:
                    continue
                decision = route(comment)
                if decision is None:
                    continue
                digest = body_revision(comment)
                previous = revisions.get(str(comment_id))
                if previous is None:
                    if not dry_run:
                        revisions[str(comment_id)] = digest
                        atomic_text(REVISIONS, json.dumps(revisions))
                    continue
                if previous == digest:
                    continue
                target, handoff = decision
                event_key = f"{comment_id}-{digest}"
                if dry_run:
                    print(json.dumps({"id": comment_id, "revision": digest,
                                      "cursor": cursor, "route": decision}, ensure_ascii=False))
                    continue
                if event_key not in events:
                    status = "EXTERNAL" if target in EXTERNAL_ROLES else "NEW"
                    events[event_key] = {
                        "comment_id": comment_id, "revision": digest, "edited": True,
                        "role": target, "handoff": handoff, "status": status,
                        "detected_at": time.time(), "queued_at": None,
                    }
                    save_events(events)
                    log(f"Detected edited handoff {comment_id} revision {digest} for {target}")
                revisions[str(comment_id)] = digest
                atomic_text(REVISIONS, json.dumps(revisions))
            for comment in comments:
                comment_id = int(comment["databaseId"])
                decision = route(comment)
                if dry_run:
                    print(json.dumps({"id": comment_id, "cursor": cursor, "route": decision}, ensure_ascii=False))
                    continue
                if decision is None:
                    log(f"Skipped non-routing comment {comment_id}; cursor advanced")
                else:
                    target, handoff = decision
                    if str(comment_id) not in events:
                        legacy = read_pending() if PENDING.exists() else {}
                        status = ("EXTERNAL" if target in EXTERNAL_ROLES else
                                  "QUEUED" if legacy.get("id") == comment_id else "NEW")
                        events[str(comment_id)] = {
                            "comment_id": comment_id, "revision": body_revision(comment),
                            "edited": False, "role": target, "handoff": handoff,
                            "status": status,
                            "detected_at": time.time(),
                            "queued_at": legacy.get("queued_at") if status == "QUEUED" else None,
                        }
                        save_events(events)
                        if status == "EXTERNAL":
                            log(f"External role {target} owns comment {comment_id}; no chat wake")
                revisions[str(comment_id)] = body_revision(comment)
                atomic_text(REVISIONS, json.dumps(revisions))
                # This is the scan cursor. Per-comment delivery state is in EVENTS.
                atomic_text(STATE, f"{comment_id}\n")
                cursor = comment_id
            if dry_run:
                return
            for event_id, event in sorted(events.items(),
                                          key=lambda item: (int(item[0].split("-", 1)[0]), item[0])):
                status = event.get("status")
                ack_path = ACK_DIR / f"{event_id}.json"
                if ack_path.exists() and status != "RETRY":
                    ack = json.loads(ack_path.read_text(encoding="utf-8"))
                    if ack.get("status") in ("DELIVERED", "BLOCKED", "SKIPPED"):
                        if status != ack["status"]:
                            event["status"] = ack["status"]
                            save_events(events)
                        if (ack["status"] == "DELIVERED" and ack.get("delivered_at") and
                                not event.get("result_alerted_at") and
                                time.time() - ack["delivered_at"] >= RESULT_TIMEOUT_SECONDS):
                            source_id = int(event.get("comment_id", event_id.split("-", 1)[0]))
                            later, _ = unseen_comments(source_id)
                            if not any(consumes_handoff(item, event["role"], event["handoff"])
                                       for item in later):
                                alert = (f"PR #{PR_NUMBER} event {event_id} was delivered to "
                                         f"{event['role']} but has no later durable result after "
                                         f"{RESULT_TIMEOUT_SECONDS // 3600} hours. Check chat status "
                                         "and GitHub; recover without duplicate delivery.")
                                command([executable("codex"), "queue", "--thread",
                                         ORCHESTRATOR_THREAD, "--message", alert])
                                event["result_alerted_at"] = time.time()
                                save_events(events)
                                log(f"Alerted orchestrator: no result for {event_id}")
                        continue
                if status == "NEW" or status == "RETRY":
                    preflight = prepare_event(event_id)
                    if preflight["status"] == "SKIPPED":
                        event["status"] = "SKIPPED"
                        save_events(events)
                        continue
                    if preflight["status"] != "READY":
                        event["status"] = "BLOCKED"
                        atomic_text(ack_path, json.dumps(preflight, ensure_ascii=False))
                        save_events(events)
                        alert = (f"PR #{PR_NUMBER} event {event_id} cannot route: "
                                 f"{preflight.get('reason', preflight['status'])}. "
                                 f"Inspect {EVENTS} and live PR state.")
                        command([executable("codex"), "queue", "--thread",
                                 ORCHESTRATOR_THREAD, "--message", alert])
                        log(f"Blocked event {event_id}: {preflight}")
                        continue
                    event["status"] = "QUEUE_INTENT"
                    event["queued_at"] = time.time()
                    save_events(events)
                    message = (f"User resumed routing. Deliver event {event_id} to {preflight['target_uuid']} "
                               f"({preflight['role']}); ack {ack_path}. Follow "
                               f"{ROOT / '.agents/workflows/HANDOFF-ROUTER.md'}.")
                    command([executable("codex"), "queue", "--thread", router_thread(),
                             "--message", message])
                    event["status"] = "QUEUED"
                    save_events(events)
                    log(f"Queued comment {event_id} ({event['handoff']}) for {event['role']}")
                elif status in ("QUEUED", "QUEUE_INTENT") and event.get("queued_at"):
                    if time.time() - event["queued_at"] >= 900 and not event.get("alerted_at"):
                        alert = (f"PR #{PR_NUMBER} router event {event_id} ({event['handoff']}) for "
                                 f"{event['role']} has not been acknowledged in 15 minutes. "
                                 f"Check router {router_thread()}, {EVENTS}, and live PR state. "
                                 "Resolve without duplicate role delivery; other events continue.")
                        command([executable("codex"), "queue", "--thread",
                                 ORCHESTRATOR_THREAD, "--message", alert])
                        event["alerted_at"] = time.time()
                        save_events(events)
                        log(f"Alerted orchestrator: unacknowledged comment {event_id}")
            # Chat health is checked only when a delivery fails or a handoff
            # remains unacknowledged. Idle polls never wake a model.
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prepare-event", metavar="EVENT_KEY")
    args = parser.parse_args(argv)
    configure(args.config)
    if args.prepare_event:
        try:
            print(json.dumps(prepare_event(args.prepare_event), ensure_ascii=False))
        except Exception as exc:
            print(json.dumps({"status": "BLOCKED", "reason":
                              f"{type(exc).__name__}: {str(exc)[:300]}"}, ensure_ascii=False))
        return
    if not ROUTING_ENABLED and not args.dry_run:
        print("ROUTER_PAUSED")
        return
    try:
        poll(args.dry_run)
        if not args.dry_run and ERROR_STATE.exists():
            ERROR_STATE.unlink()
    except Exception as exc:
        log(f"ERROR {type(exc).__name__}: {exc}")
        if args.dry_run:
            raise
        state = read_json(ERROR_STATE)
        count = state.get("consecutive", 0) + 1
        state["consecutive"] = count
        state["last_error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
        state["last_at"] = time.time()
        if count >= 3 and not state.get("alerted_at"):
            message = (f"Local PR #{PR_NUMBER} poller failed {count} consecutive runs: "
                       f"{state['last_error']}. Check {LOG}, config {args.config}, and "
                       "GitHub CLI/network health. PR routing may be delayed.")
            try:
                command([executable("codex"), "queue", "--thread",
                         ORCHESTRATOR_THREAD, "--message", message])
                state["alerted_at"] = time.time()
            except Exception as alert_exc:
                log(f"ERROR orchestrator alert failed: {alert_exc}")
        atomic_text(ERROR_STATE, json.dumps(state))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
