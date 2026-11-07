#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { argv, stdout, stderr, exit } from "node:process";
import { CloudRoleBridge } from "./bridge-lib.mjs";
import { parseResultEnvelope, validateResultEnvelope } from "./envelope.mjs";
import { SessionHostError } from "../../../../dist/packages/protocol/src/errors.js";

function parseArgs(tokens) {
  const [command, ...rest] = tokens;
  const values = new Map();
  const flags = new Set();

  for (let i = 0; i < rest.length; i++) {
    const token = rest[i];
    if (!token?.startsWith("--")) {
      throw new Error(`Unexpected argument: ${token}`);
    }
    const key = token.slice(2);
    const next = rest[i + 1];
    if (!next || next.startsWith("--")) {
      flags.add(key);
    } else {
      values.set(key, next);
      i++;
    }
  }

  return { command, values, flags };
}

function required(values, key) {
  const val = values.get(key);
  if (!val) {
    throw new Error(`Missing required --${key}`);
  }
  return val;
}

async function readMessage(values, inlineKey, fileKey) {
  const inline = values.get(inlineKey);
  const file = values.get(fileKey);
  if (inline && file) {
    throw new Error(`Use either --${inlineKey} or --${fileKey}, not both.`);
  }
  if (inline) return inline;
  if (file) return readFile(resolve(file), "utf8");
  throw new Error(`Provide --${inlineKey} or --${fileKey}.`);
}

function usage() {
  return `Cloud Role Bridge CLI (temporary local tooling)\n\n` +
    `Commands:\n` +
    `  status         [--role-slot ID]\n` +
    `  ensure-role    --role-slot ID [--bootstrap-if-missing --project URL] [--profile ID] [--cdp-endpoint URL]\n` +
    `  create-chat    --session ID --project URL (--bootstrap TEXT | --bootstrap-file FILE) [--profile ID] --cdp-endpoint URL\n` +
    `  rename-chat    --session ID --locator URL --title TITLE --cdp-endpoint URL\n` +
    `  delete-chat    --session bridge-validation-ID --locator URL --title TITLE --cdp-endpoint URL\n` +
    `  send-role      --role-slot ID --sha FULL_SHA (--prompt TEXT | --prompt-file FILE) [--purpose PURPOSE] [--issue N] [--pr N] [--request-id ID] --cdp-endpoint URL\n` +
    `  wait-response  --role-slot ID [--request-id ID] [--sha FULL_SHA] [--timeout SECONDS] --cdp-endpoint URL\n` +
    `  replace-role   --role-slot ID --expected-generation N [--session ID] [--project URL] [--bootstrap TEXT | --bootstrap-file FILE] --cdp-endpoint URL\n` +
    `  parse-result   (--file FILE | --text TEXT) [--request-id ID] [--role ROLE] [--sha SHA]\n`;
}

async function main() {
  const parsed = parseArgs(argv.slice(2));
  const bridge = new CloudRoleBridge({
    browserRuntime: parsed.values.get("browser"),
    cdpEndpoint: parsed.values.get("cdp-endpoint"),
    runtimeRoot: parsed.values.get("runtime-root"),
  });

  switch (parsed.command) {
    case "status": {
      const roleSlot = parsed.values.get("role-slot");
      const result = await bridge.getStatus(roleSlot);
      stdout.write(`${JSON.stringify(result, null, 2)}\n`);
      return;
    }

    case "ensure-role": {
      const roleSlot = required(parsed.values, "role-slot");
      const bootstrapIfMissing = parsed.flags.has("bootstrap-if-missing");
      const profileId = parsed.values.get("profile") ?? "default";
      const result = await bridge.ensureRole(roleSlot, {
        bootstrapIfMissing,
        profileId,
        projectLocator: parsed.values.get("project"),
      });
      stdout.write(`${JSON.stringify(result, null, 2)}\n`);
      return;
    }

    case "create-chat": {
      const bootstrapMessage = await readMessage(parsed.values, "bootstrap", "bootstrap-file");
      const result = await bridge.createChat({
        sessionId: required(parsed.values, "session"),
        projectLocator: required(parsed.values, "project"),
        bootstrapMessage,
        profileId: parsed.values.get("profile") ?? "default",
      });
      stdout.write(`${JSON.stringify(result, null, 2)}\n`);
      return;
    }

    case "rename-chat": {
      const result = await bridge.renameChat({
        sessionId: required(parsed.values, "session"),
        expectedLocator: required(parsed.values, "locator"),
        title: required(parsed.values, "title"),
      });
      stdout.write(`${JSON.stringify(result, null, 2)}\n`);
      return;
    }

    case "delete-chat": {
      const result = await bridge.deleteChat({
        sessionId: required(parsed.values, "session"),
        expectedLocator: required(parsed.values, "locator"),
        title: required(parsed.values, "title"),
      });
      stdout.write(`${JSON.stringify(result, null, 2)}\n`);
      return;
    }

    case "send-role": {
      const roleSlot = required(parsed.values, "role-slot");
      const prompt = await readMessage(parsed.values, "prompt", "prompt-file");
      const candidateSha = required(parsed.values, "sha");
      const purpose = parsed.values.get("purpose") ?? "GENERAL_TASK";
      const issue = parsed.values.get("issue") ?? "3";
      const pr = parsed.values.get("pr") ?? "4";
      const requestId = parsed.values.get("request-id");

      const result = await bridge.sendRole({
        roleSlot,
        taskPrompt: prompt,
        candidateSha,
        purpose,
        issue,
        pr,
        requestId,
      });
      stdout.write(`${JSON.stringify(result, null, 2)}\n`);
      return;
    }

    case "wait-response": {
      const roleSlot = required(parsed.values, "role-slot");
      const requestId = parsed.values.get("request-id");
      const expectedSha = parsed.values.get("sha");
      const timeoutSec = parsed.values.get("timeout");
      const timeoutMs = timeoutSec ? Number.parseInt(timeoutSec, 10) * 1000 : 120_000;

      const result = await bridge.waitRoleResponse({
        roleSlot,
        requestId,
        expectedSha,
        timeoutMs,
      });
      stdout.write(`${JSON.stringify(result, null, 2)}\n`);
      return;
    }

    case "replace-role": {
      const roleSlot = required(parsed.values, "role-slot");
      const expectedGenStr = required(parsed.values, "expected-generation");
      const expectedGen = Number.parseInt(expectedGenStr, 10);
      const newSessionId = parsed.values.get("session");
      const bootstrap = parsed.values.get("bootstrap");
      const bootstrapFile = parsed.values.get("bootstrap-file");
      const profileId = parsed.values.get("profile") ?? "default";
      const projectLocator = parsed.values.get("project");

      const result = await bridge.replaceRole({
        roleSlot,
        expectedGeneration: expectedGen,
        newSessionId,
        bootstrapMessage: bootstrap,
        bootstrapFile,
        profileId,
        projectLocator,
      });
      stdout.write(`${JSON.stringify(result, null, 2)}\n`);
      return;
    }

    case "parse-result": {
      const text = await readMessage(parsed.values, "text", "file");
      const parsedEnvelope = parseResultEnvelope(text);
      const expectedRequestId = parsed.values.get("request-id");
      const expectedRole = parsed.values.get("role");
      const expectedSha = parsed.values.get("sha");

      const validated = validateResultEnvelope(parsedEnvelope, {
        requestId: expectedRequestId,
        role: expectedRole,
        candidateSha: expectedSha,
      });
      stdout.write(`${JSON.stringify(validated, null, 2)}\n`);
      return;
    }

    case "help":
    case "--help":
    case undefined:
      stdout.write(usage());
      return;

    default:
      throw new Error(`Unknown command: ${parsed.command}\n\n${usage()}`);
  }
}

main().catch((err) => {
  if (err instanceof SessionHostError) {
    stderr.write(`${JSON.stringify({ code: err.code, message: err.message })}\n`);
  } else {
    stderr.write(`${JSON.stringify({ code: err.code || "BRIDGE_ERROR", message: err.message || String(err) })}\n`);
  }
  exit(1);
});
