import { randomUUID } from "node:crypto";

export class EnvelopeError extends Error {
  constructor(code, message, details) {
    super(message);
    this.name = "EnvelopeError";
    this.code = code;
    this.details = details;
  }
}

/**
 * Creates an outgoing CLOUD_ROLE_REQUEST v1 payload.
 */
export function createRequestEnvelope(params) {
  const {
    role,
    repository = "tosumitdhaka/agent-control-plane",
    issue = "3",
    pr = "4",
    candidateSha,
    purpose,
    taskPrompt,
    requestId,
  } = params;

  if (!role || typeof role !== "string") {
    throw new EnvelopeError("INVALID_ENVELOPE_PARAM", "Role is required and must be a string.");
  }
  if (!["DESIGN_OWNER", "REVIEWER"].includes(role)) {
    throw new EnvelopeError("INVALID_ENVELOPE_PARAM", `Unsupported role: "${role}".`);
  }
  if (!candidateSha || typeof candidateSha !== "string" || !/^[0-9a-fA-F]{40}$/.test(candidateSha)) {
    throw new EnvelopeError("INVALID_ENVELOPE_PARAM", `Invalid candidate_sha: "${candidateSha}". Supply the exact 40-character git commit SHA.`);
  }
  if (!purpose || typeof purpose !== "string") {
    throw new EnvelopeError("INVALID_ENVELOPE_PARAM", "Purpose is required and must be a string.");
  }
  if (!taskPrompt || typeof taskPrompt !== "string" || taskPrompt.trim().length === 0) {
    throw new EnvelopeError("INVALID_ENVELOPE_PARAM", "Task prompt is required.");
  }

  const resolvedRequestId = requestId || `req-${Date.now()}-${randomUUID().slice(0, 8)}`;
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(resolvedRequestId)) {
    throw new EnvelopeError("INVALID_ENVELOPE_PARAM", "request_id must be a safe 1-128 character identifier.");
  }

  const header = [
    "CLOUD_ROLE_REQUEST v1",
    "",
    `request_id: ${resolvedRequestId}`,
    `role: ${role}`,
    `repository: ${repository}`,
    `issue: ${issue}`,
    `pr: ${pr}`,
    `candidate_sha: ${candidateSha}`,
    `purpose: ${purpose}`,
    "",
  ].join("\n");

  return {
    requestId: resolvedRequestId,
    role,
    repository,
    issue: String(issue),
    pr: String(pr),
    candidateSha,
    purpose,
    rawText: `${header}${taskPrompt.trim()}\n`,
  };
}

/**
 * Parses a CLOUD_ROLE_RESULT v1 payload from raw assistant text.
 */
export function parseResultEnvelope(rawText) {
  if (typeof rawText !== "string" || rawText.trim().length === 0) {
    throw new EnvelopeError("EMPTY_RESPONSE", "Assistant response is empty.");
  }

  const normalized = rawText.replace(/\r\n/g, "\n").replace(/^\uFEFF/, "").trim();
  const lines = normalized.split("\n");
  if (lines.shift()?.trim() !== "CLOUD_ROLE_RESULT v1") {
    throw new EnvelopeError(
      "INVALID_RESULT_ENVELOPE",
      "Response must start with CLOUD_ROLE_RESULT v1.",
      { rawSnippet: rawText.slice(0, 300) },
    );
  }

  const headerLines = [];
  while (lines.length > 0 && lines[0].trim() !== "") {
    headerLines.push(lines.shift());
  }
  while (lines.length > 0 && lines[0].trim() === "") lines.shift();
  return parseHeaderLines(headerLines.join("\n"), lines.join("\n"), rawText);
}

function parseHeaderLines(headerBlock, bodyBlock, rawText) {
  const lines = headerBlock.split("\n");
  const fields = {};

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const colonIdx = trimmed.indexOf(":");
    if (colonIdx === -1) continue;
    const key = trimmed.slice(0, colonIdx).trim().toLowerCase();
    const value = trimmed.slice(colonIdx + 1).trim();
    if (Object.prototype.hasOwnProperty.call(fields, key)) {
      throw new EnvelopeError("INVALID_RESULT_ENVELOPE", `Duplicate result header: ${key}`);
    }
    fields[key] = value;
  }

  const requestId = fields["request_id"];
  const role = fields["role"];
  const reviewedSha = fields["reviewed_sha"];
  const status = fields["status"];

  if (!requestId) {
    throw new EnvelopeError("INVALID_RESULT_ENVELOPE", "Missing required header: request_id");
  }
  if (!role) {
    throw new EnvelopeError("INVALID_RESULT_ENVELOPE", "Missing required header: role");
  }
  if (!reviewedSha) {
    throw new EnvelopeError("INVALID_RESULT_ENVELOPE", "Missing required header: reviewed_sha");
  }
  if (!status) {
    throw new EnvelopeError("INVALID_RESULT_ENVELOPE", "Missing required header: status");
  }
  if (!/^[0-9a-fA-F]{40}$/.test(reviewedSha)) {
    throw new EnvelopeError("INVALID_RESULT_ENVELOPE", "reviewed_sha must be the exact 40-character commit SHA.");
  }

  const allowedStatuses = {
    DESIGN_OWNER: new Set(["DESIGN_SCHEMA_FREEZE_APPROVED", "PRE_GATE_APPROVED", "CHANGES_REQUIRED", "DECISION_PENDING"]),
    REVIEWER: new Set(["SOURCE_REVIEW_PASS", "PRE_GATE_APPROVED", "CHANGES_REQUIRED", "BLOCKED"]),
  };
  if (!allowedStatuses[role]?.has(status)) {
    throw new EnvelopeError(
      "INVALID_RESULT_ENVELOPE",
      `Unsupported status "${status}" for role "${role}".`,
    );
  }

  return {
    version: "v1",
    requestId,
    role,
    reviewedSha,
    status,
    body: (bodyBlock || "").trim(),
    rawText,
  };
}

/**
 * Validates a parsed result envelope against the expected request and lifecycle state.
 */
export function validateResultEnvelope(parsed, expected) {
  if (expected.requestId && parsed.requestId !== expected.requestId) {
    throw new EnvelopeError(
      "REQUEST_ID_MISMATCH",
      `Response request_id mismatch: expected "${expected.requestId}", got "${parsed.requestId}".`,
      { expectedRequestId: expected.requestId, receivedRequestId: parsed.requestId }
    );
  }

  if (expected.role) {
    const normalizedExpected = expected.role.replace(/[-_]/g, "").toUpperCase();
    const normalizedReceived = parsed.role.replace(/[-_]/g, "").toUpperCase();
    if (normalizedExpected !== normalizedReceived) {
      throw new EnvelopeError(
        "ROLE_MISMATCH",
        `Response role mismatch: expected "${expected.role}", got "${parsed.role}".`,
        { expectedRole: expected.role, receivedRole: parsed.role }
      );
    }
  }

  if (expected.candidateSha) {
    const exp = expected.candidateSha.toLowerCase();
    const rec = parsed.reviewedSha.toLowerCase();
    const isShaMatch = exp === rec;

    if (!isShaMatch) {
      throw new EnvelopeError(
        "SHA_MISMATCH",
        `Response reviewed_sha mismatch: expected "${expected.candidateSha}", got "${parsed.reviewedSha}".`,
        { expectedSha: expected.candidateSha, receivedSha: parsed.reviewedSha }
      );
    }
  }

  if (expected.expectedGeneration !== undefined && expected.currentActiveGeneration !== undefined) {
    if (expected.expectedGeneration !== expected.currentActiveGeneration) {
      throw new EnvelopeError(
        "STALE_SESSION_GENERATION",
        `Role session generation changed during request processing: expected ${expected.expectedGeneration}, current active is ${expected.currentActiveGeneration}.`,
        { expectedGeneration: expected.expectedGeneration, currentGeneration: expected.currentActiveGeneration }
      );
    }
  }

  return {
    valid: true,
    requestId: parsed.requestId,
    role: parsed.role,
    reviewedSha: parsed.reviewedSha,
    status: parsed.status,
    body: parsed.body,
  };
}
