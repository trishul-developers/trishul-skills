import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import {
  createRequestEnvelope,
  parseResultEnvelope,
  validateResultEnvelope,
  EnvelopeError,
} from "../scripts/envelope.mjs";
import { CloudRoleBridge, ROLE_SLOT_DEFINITIONS } from "../scripts/bridge-lib.mjs";
import { observeAssistantResponse } from "../scripts/response-observer.mjs";

describe("CloudRoleBridge - Request Envelope", () => {
  it("formats outgoing CLOUD_ROLE_REQUEST v1 properly with all required fields", () => {
    const envelope = createRequestEnvelope({
      role: "DESIGN_OWNER",
      repository: "tosumitdhaka/agent-control-plane",
      issue: "3",
      pr: "4",
      candidateSha: "01f448b174c69f2039581384534874152c2fafd3",
      purpose: "DESIGN_SCHEMA_FREEZE",
      taskPrompt: "Please review the Gate 1 relational schema package.",
      requestId: "req-test-1234",
    });

    assert.equal(envelope.requestId, "req-test-1234");
    assert.equal(envelope.role, "DESIGN_OWNER");
    assert.equal(envelope.candidateSha, "01f448b174c69f2039581384534874152c2fafd3");
    assert.equal(envelope.purpose, "DESIGN_SCHEMA_FREEZE");
    assert.match(envelope.rawText, /^CLOUD_ROLE_REQUEST v1\n/);
    assert.match(envelope.rawText, /request_id: req-test-1234/);
    assert.match(envelope.rawText, /role: DESIGN_OWNER/);
    assert.match(envelope.rawText, /candidate_sha: 01f448b174c69f2039581384534874152c2fafd3/);
    assert.match(envelope.rawText, /purpose: DESIGN_SCHEMA_FREEZE/);
    assert.match(envelope.rawText, /Please review the Gate 1 relational schema package\.\n$/);
  });

  it("generates a unique request_id when omitted", () => {
    const env1 = createRequestEnvelope({
      role: "REVIEWER",
      candidateSha: "01f448b174c69f2039581384534874152c2fafd3",
      purpose: "SOURCE_REVIEW",
      taskPrompt: "Check git diff",
    });
    const env2 = createRequestEnvelope({
      role: "REVIEWER",
      candidateSha: "01f448b174c69f2039581384534874152c2fafd3",
      purpose: "SOURCE_REVIEW",
      taskPrompt: "Check git diff",
    });

    assert.ok(env1.requestId.startsWith("req-"));
    assert.ok(env2.requestId.startsWith("req-"));
    assert.notEqual(env1.requestId, env2.requestId);
  });

  it("rejects invalid role, invalid SHA, or empty prompt", () => {
    assert.throws(
      () =>
        createRequestEnvelope({
          role: "",
          candidateSha: "01f448b",
          purpose: "TEST",
          taskPrompt: "valid prompt",
        }),
      (err) => err instanceof EnvelopeError && err.code === "INVALID_ENVELOPE_PARAM"
    );

    assert.throws(
      () =>
        createRequestEnvelope({
          role: "DESIGN_OWNER",
          candidateSha: "not-a-sha!",
          purpose: "TEST",
          taskPrompt: "valid prompt",
        }),
      (err) => err instanceof EnvelopeError && err.code === "INVALID_ENVELOPE_PARAM"
    );

    assert.throws(
      () =>
        createRequestEnvelope({
          role: "DESIGN_OWNER",
          candidateSha: "01f448b",
          purpose: "TEST",
          taskPrompt: "   ",
        }),
      (err) => err instanceof EnvelopeError && err.code === "INVALID_ENVELOPE_PARAM"
    );
  });
});

describe("CloudRoleBridge - Result Envelope Parser & Validator", () => {
  it("parses valid CLOUD_ROLE_RESULT v1 response", () => {
    const raw = `CLOUD_ROLE_RESULT v1
request_id: req-test-1234
role: DESIGN_OWNER
reviewed_sha: 01f448b174c69f2039581384534874152c2fafd3
status: DESIGN_SCHEMA_FREEZE_APPROVED

The proposed schema conforms to Architecture Amendment A-01 and ADR-004.
All 8 relational tables are correctly normalized.`;

    const parsed = parseResultEnvelope(raw);
    assert.equal(parsed.requestId, "req-test-1234");
    assert.equal(parsed.role, "DESIGN_OWNER");
    assert.equal(parsed.reviewedSha, "01f448b174c69f2039581384534874152c2fafd3");
    assert.equal(parsed.status, "DESIGN_SCHEMA_FREEZE_APPROVED");
    assert.ok(parsed.body.includes("The proposed schema conforms to Architecture Amendment A-01"));
  });

  it("accepts PRE_GATE_APPROVED from the Reviewer role", () => {
    const raw = `CLOUD_ROLE_RESULT v1
request_id: req-pregate-approved
role: REVIEWER
reviewed_sha: 4329a40f4acd5d807f2fd32f4d79ff418eea81e7
status: PRE_GATE_APPROVED

Gate 3 pre-gate package approved.`;

    const parsed = parseResultEnvelope(raw);
    assert.equal(parsed.status, "PRE_GATE_APPROVED");
    assert.equal(parsed.role, "REVIEWER");
  });

  it("rejects prose before the result envelope", () => {
    const raw = `Here is my verdict:

CLOUD_ROLE_RESULT v1
request_id: req-999
role: REVIEWER
reviewed_sha: 01f448b174c69f2039581384534874152c2fafd3
status: SOURCE_REVIEW_PASS

All checks passed.`;

    assert.throws(
      () => parseResultEnvelope(raw),
      (err) => err instanceof EnvelopeError && err.code === "INVALID_RESULT_ENVELOPE",
    );
  });

  it("rejects response without CLOUD_ROLE_RESULT header", () => {
    const invalidText = "Looks good to me! Approved.";
    assert.throws(
      () => parseResultEnvelope(invalidText),
      (err) => err instanceof EnvelopeError && err.code === "INVALID_RESULT_ENVELOPE"
    );
  });

  it("rejects response with missing header fields", () => {
    const missingStatus = `CLOUD_ROLE_RESULT v1
request_id: req-123
role: DESIGN_OWNER
reviewed_sha: 01f448b

Missing status field!`;

    assert.throws(
      () => parseResultEnvelope(missingStatus),
      (err) => err instanceof EnvelopeError && err.code === "INVALID_RESULT_ENVELOPE"
    );
  });

  it("validateResultEnvelope succeeds when request_id, role, SHA match", () => {
    const parsed = {
      version: "v1",
      requestId: "req-1234",
      role: "DESIGN_OWNER",
      reviewedSha: "01f448b174c69f2039581384534874152c2fafd3",
      status: "DESIGN_SCHEMA_FREEZE_APPROVED",
      body: "OK",
    };

    const validated = validateResultEnvelope(parsed, {
      requestId: "req-1234",
      role: "DESIGN_OWNER",
      candidateSha: "01f448b174c69f2039581384534874152c2fafd3",
      expectedGeneration: 1,
      currentActiveGeneration: 1,
    });

    assert.equal(validated.valid, true);
    assert.equal(validated.requestId, "req-1234");
  });

  it("validateResultEnvelope fails closed on request_id mismatch", () => {
    const parsed = {
      version: "v1",
      requestId: "req-wrong-id",
      role: "DESIGN_OWNER",
      reviewedSha: "01f448b174c69f2039581384534874152c2fafd3",
      status: "DESIGN_SCHEMA_FREEZE_APPROVED",
      body: "OK",
    };

    assert.throws(
      () =>
        validateResultEnvelope(parsed, {
          requestId: "req-expected-id",
          role: "DESIGN_OWNER",
        }),
      (err) => err instanceof EnvelopeError && err.code === "REQUEST_ID_MISMATCH"
    );
  });

  it("validateResultEnvelope fails closed on role mismatch", () => {
    const parsed = {
      version: "v1",
      requestId: "req-1234",
      role: "REVIEWER",
      reviewedSha: "01f448b174c69f2039581384534874152c2fafd3",
      status: "SOURCE_REVIEW_PASS",
      body: "OK",
    };

    assert.throws(
      () =>
        validateResultEnvelope(parsed, {
          requestId: "req-1234",
          role: "DESIGN_OWNER",
        }),
      (err) => err instanceof EnvelopeError && err.code === "ROLE_MISMATCH"
    );
  });

  it("validateResultEnvelope fails closed on SHA mismatch", () => {
    const parsed = {
      version: "v1",
      requestId: "req-1234",
      role: "DESIGN_OWNER",
      reviewedSha: "deadbeef1234567890abcdef1234567890abcdef",
      status: "DESIGN_SCHEMA_FREEZE_APPROVED",
      body: "OK",
    };

    assert.throws(
      () =>
        validateResultEnvelope(parsed, {
          requestId: "req-1234",
          role: "DESIGN_OWNER",
          candidateSha: "01f448b174c69f2039581384534874152c2fafd3",
        }),
      (err) => err instanceof EnvelopeError && err.code === "SHA_MISMATCH"
    );
  });

  it("validateResultEnvelope fails closed on stale generation", () => {
    const parsed = {
      version: "v1",
      requestId: "req-1234",
      role: "DESIGN_OWNER",
      reviewedSha: "01f448b174c69f2039581384534874152c2fafd3",
      status: "DESIGN_SCHEMA_FREEZE_APPROVED",
      body: "OK",
    };

    assert.throws(
      () =>
        validateResultEnvelope(parsed, {
          requestId: "req-1234",
          role: "DESIGN_OWNER",
          expectedGeneration: 1,
          currentActiveGeneration: 2, // generation advanced!
        }),
      (err) => err instanceof EnvelopeError && err.code === "STALE_SESSION_GENERATION"
    );
  });
});

describe("CloudRoleBridge - Local Operations & Role Definitions", () => {
  it("defines standard Phase 2 role slots correctly", () => {
    assert.deepEqual(Object.keys(ROLE_SLOT_DEFINITIONS), [
      "phase2-design-owner",
      "phase2-reviewer",
    ]);
    assert.equal(ROLE_SLOT_DEFINITIONS["phase2-design-owner"].logicalRole, "DESIGN_OWNER");
    assert.equal(ROLE_SLOT_DEFINITIONS["phase2-reviewer"].logicalRole, "REVIEWER");
  });

  it("reports NOT_ACTIVE status when no sessions are bound (zero provider interaction)", async () => {
    const tempDir = await mkdtemp(join(tmpdir(), "bridge-test-"));
    try {
      const bridge = new CloudRoleBridge({ runtimeRoot: tempDir });
      const status = await bridge.getStatus();

      assert.equal(status["phase2-design-owner"].status, "NOT_ACTIVE");
      assert.equal(status["phase2-reviewer"].status, "NOT_ACTIVE");
      assert.equal(status["phase2-design-owner"].active_generation, null);
    } finally {
      await rm(tempDir, { recursive: true, force: true }).catch(() => {});
    }
  });

  it("ensureRole without bootstrapIfMissing returns NOT_ACTIVE without creating sessions", async () => {
    const tempDir = await mkdtemp(join(tmpdir(), "bridge-test-"));
    try {
      const bridge = new CloudRoleBridge({ runtimeRoot: tempDir });
      const result = await bridge.ensureRole("phase2-design-owner", { bootstrapIfMissing: false });

      assert.equal(result.role_slot, "phase2-design-owner");
      assert.equal(result.status, "NOT_ACTIVE");
    } finally {
      await rm(tempDir, { recursive: true, force: true }).catch(() => {});
    }
  });
});

describe("CloudRoleBridge - Response waiting", () => {
  it("waits until a response has stopped streaming and remains stable", async () => {
    const states = [
      { found: true, hasAssistantTurn: true, isStreaming: true, rawText: "partial" },
      { found: true, hasAssistantTurn: true, isStreaming: false, rawText: "complete" },
      { found: true, hasAssistantTurn: true, isStreaming: false, rawText: "complete" },
    ];
    const page = {
      evaluate: async () => states.shift() ?? states.at(-1),
      waitForTimeout: async () => undefined,
    };

    const response = await observeAssistantResponse(page, {
      requestId: "req-wait-test",
      timeoutMs: 1000,
      stabilityMs: 0,
      pollIntervalMs: 0,
    });

    assert.equal(response.requestId, "req-wait-test");
    assert.equal(response.text, "complete");
  });

  it("reports the last observer state when no assistant turn arrives", async () => {
    const page = {
      evaluate: async () => ({ found: true, hasAssistantTurn: false, isStreaming: false, reason: "WAITING_FOR_ASSISTANT_TURN" }),
      waitForTimeout: async () => undefined,
    };

    await assert.rejects(
      observeAssistantResponse(page, {
        requestId: "req-wait-timeout",
        timeoutMs: 0,
        pollIntervalMs: 0,
      }),
      (err) => err.code === "ROUTER_DELIVERY_FAILED" && /WAITING_FOR_ASSISTANT_TURN/.test(err.message),
    );
  });
});

describe("CloudRoleBridge - CLI Command Routing", () => {
  const cliPath = resolve(".agents/skills/cloud-role-bridge/scripts/bridge.mjs");

  it("prints usage on --help", async () => {
    const { spawnSync } = await import("node:child_process");
    const res = spawnSync(process.execPath, [cliPath, "--help"], { encoding: "utf8" });
    assert.equal(res.status, 0);
    assert.match(res.stdout, /Cloud Role Bridge CLI/);
    assert.match(res.stdout, /ensure-role/);
    assert.match(res.stdout, /send-role/);
    assert.match(res.stdout, /wait-response/);
    assert.match(res.stdout, /replace-role/);
  });

  it("returns status JSON for role slots via CLI", async () => {
    const { spawnSync } = await import("node:child_process");
    const tempDir = await mkdtemp(join(tmpdir(), "bridge-cli-"));
    try {
      const res = spawnSync(
        process.execPath,
        [cliPath, "status", "--runtime-root", tempDir],
        { encoding: "utf8" }
      );
      assert.equal(res.status, 0);
      const parsed = JSON.parse(res.stdout);
      assert.equal(parsed["phase2-design-owner"].status, "NOT_ACTIVE");
      assert.equal(parsed["phase2-reviewer"].status, "NOT_ACTIVE");
    } finally {
      await rm(tempDir, { recursive: true, force: true }).catch(() => {});
    }
  });

  it("parses and validates result via CLI parse-result", async () => {
    const { spawnSync } = await import("node:child_process");
    const payload = `CLOUD_ROLE_RESULT v1
request_id: req-cli-test
role: DESIGN_OWNER
reviewed_sha: 01f448b174c69f2039581384534874152c2fafd3
status: DESIGN_SCHEMA_FREEZE_APPROVED

Detailed review notes.`;

    const res = spawnSync(
      process.execPath,
      [
        cliPath,
        "parse-result",
        "--text",
        payload,
        "--request-id",
        "req-cli-test",
        "--role",
        "DESIGN_OWNER",
        "--sha",
        "01f448b174c69f2039581384534874152c2fafd3",
      ],
      { encoding: "utf8" }
    );
    assert.equal(res.status, 0);
    const parsed = JSON.parse(res.stdout);
    assert.equal(parsed.valid, true);
    assert.equal(parsed.requestId, "req-cli-test");
    assert.equal(parsed.status, "DESIGN_SCHEMA_FREEZE_APPROVED");
  });

  it("CLI parse-result fails closed when SHA mismatches", async () => {
    const { spawnSync } = await import("node:child_process");
    const payload = `CLOUD_ROLE_RESULT v1
request_id: req-cli-test
role: DESIGN_OWNER
reviewed_sha: 01f448b174c69f2039581384534874152c2fafd3
status: DESIGN_SCHEMA_FREEZE_APPROVED

Detailed review notes.`;

    const res = spawnSync(
      process.execPath,
      [
        cliPath,
        "parse-result",
        "--text",
        payload,
        "--request-id",
        "req-cli-test",
        "--role",
        "DESIGN_OWNER",
        "--sha",
        "9999999999999999999999999999999999999999",
      ],
      { encoding: "utf8" }
    );
    assert.equal(res.status, 1);
    const err = JSON.parse(res.stderr);
    assert.equal(err.code, "SHA_MISMATCH");
  });
});
