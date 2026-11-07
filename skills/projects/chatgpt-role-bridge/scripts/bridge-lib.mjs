import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import {
  ChatGptBrowserStrategy,
  LocalSessionStore,
  LifecycleStore,
  LifecycleManager,
  ChatGptSessionAdapter,
  SessionHostError,
  isCanonicalConversationUrl,
  validateChatGptLocator,
  validateProjectLocator,
  requirePositiveProjectAuthority,
} from "./acp-loader.mjs";
import {
  createRequestEnvelope,
  parseResultEnvelope,
  validateResultEnvelope,
} from "./envelope.mjs";
import { observeAssistantResponse } from "./response-observer.mjs";

export const ROLE_SLOT_DEFINITIONS = {
  "phase2-design-owner": {
    logicalRole: "DESIGN_OWNER",
    bootstrapFile: "phase2-design-owner-bootstrap.txt",
    description: "ChatGPT DESIGN_OWNER: final design authority for architecture, schema, contracts, and ADRs.",
  },
  "phase2-reviewer": {
    logicalRole: "REVIEWER",
    bootstrapFile: "phase2-reviewer-bootstrap.txt",
    description: "ChatGPT REVIEWER: independent read-only reviewer for exact candidate SHAs.",
  },
};

export class CloudRoleBridge {
  constructor(options = {}) {
    const cwd = options.cwd ?? process.cwd();
    this.runtimeRoot = resolve(options.runtimeRoot ?? resolve(cwd, ".session-host"));
    this.stateFile = resolve(this.runtimeRoot, "state", "sessions.json");
    this.lifecycleFile = resolve(this.runtimeRoot, "state", "lifecycle.json");
    this.bridgeStateDir = resolve(this.runtimeRoot, "bridge");

    this.browserRuntime = options.browserRuntime;
    this.cdpEndpoint = options.cdpEndpoint;

    this.strategy = new ChatGptBrowserStrategy({
      runtimeRoot: this.runtimeRoot,
      ...(this.browserRuntime === undefined ? {} : { browserRuntime: this.browserRuntime }),
      ...(this.cdpEndpoint === undefined ? {} : { cdpEndpoint: this.cdpEndpoint }),
    });

    this.sessionStore = new LocalSessionStore(this.stateFile);
    this.adapter = new ChatGptSessionAdapter(this.strategy, this.sessionStore);
    this.lifecycleStore = new LifecycleStore(this.lifecycleFile);
    this.lifecycleManager = new LifecycleManager(
      this.lifecycleStore,
      this.sessionStore,
      this.adapter
    );
  }

  /**
   * Status of role slots and current active sessions.
   */
  async getStatus(roleSlot) {
    const slotsToQuery = roleSlot ? [roleSlot] : Object.keys(ROLE_SLOT_DEFINITIONS);
    const results = {};

    for (const slot of slotsToQuery) {
      const def = ROLE_SLOT_DEFINITIONS[slot];
      try {
        const active = await this.lifecycleManager.getActiveBinding(slot);
        let sessionMeta = null;
        try {
          sessionMeta = await this.sessionStore.get(active.active_session_id);
        } catch {
          // session metadata missing
        }

        const lastReq = await this.readLastRequest(slot);

        results[slot] = {
          role_slot: slot,
          logical_role: def?.logicalRole ?? "UNKNOWN",
          status: "ACTIVE",
          active_generation: active.active_generation,
          active_session_id: active.active_session_id,
          locator: sessionMeta?.locator ?? null,
          surface: sessionMeta?.surface ?? null,
          profile_id: sessionMeta?.profile_id ?? null,
          verified_at: sessionMeta?.verified_at ?? null,
          last_request: lastReq,
        };
      } catch (err) {
        results[slot] = {
          role_slot: slot,
          logical_role: def?.logicalRole ?? "UNKNOWN",
          status: "NOT_ACTIVE",
          active_generation: null,
          active_session_id: null,
          locator: null,
          surface: null,
          reason: err instanceof SessionHostError ? err.code : String(err),
        };
      }
    }

    return results;
  }

  /**
   * Ensures a role has an ACTIVE session.
   * If bootstrapIfMissing is true and role is not active, creates and binds generation 1.
   */
  async ensureRole(roleSlot, options = {}) {
    const { bootstrapIfMissing = false, profileId = "default" } = options;
    const projectLocator = validateProjectLocator(options.projectLocator);
    const def = ROLE_SLOT_DEFINITIONS[roleSlot];

    try {
      const active = await this.lifecycleManager.getActiveBinding(roleSlot);
      const session = await this.sessionStore.get(active.active_session_id);
      if (projectLocator && session.project_locator !== projectLocator) {
        throw new SessionHostError(
          "PROJECT_UNVERIFIED",
          `Role slot "${roleSlot}" is bound to a different Project than requested.`,
        );
      }
      return {
        role_slot: roleSlot,
        status: "ACTIVE",
        active_generation: active.active_generation,
        active_session_id: active.active_session_id,
        locator: session.locator,
        surface: session.surface,
      };
    } catch (err) {
      if (err instanceof SessionHostError && err.code === "PROJECT_UNVERIFIED") {
        throw err;
      }
      if (!bootstrapIfMissing) {
        return {
          role_slot: roleSlot,
          status: "NOT_ACTIVE",
          reason: err instanceof SessionHostError ? err.code : String(err),
        };
      }

      this.requireExistingCdp();
      if (!projectLocator) {
        throw new SessionHostError(
          "PROJECT_UNVERIFIED",
          "Role bootstrap requires an explicit --project locator.",
        );
      }

      // Bootstrap a new session
      if (!def) {
        throw new SessionHostError(
          "STALE_SESSION_GENERATION",
          `Unknown role_slot "${roleSlot}". Supported: ${Object.keys(ROLE_SLOT_DEFINITIONS).join(", ")}`
        );
      }

      const resourcePath = resolve(
        dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")),
        "..",
        "resources",
        def.bootstrapFile
      );

      const bootstrapMessage = await readFile(resourcePath, "utf8");
      const sessionId = `${roleSlot}-gen1-${Date.now().toString(36)}`;

      await this.adapter.create({
        session_id: sessionId,
        profile_id: profileId,
        bootstrap_message: bootstrapMessage,
        project_locator: projectLocator,
      });

      const binding = await this.lifecycleManager.bindRoleSlot(roleSlot, sessionId, 1);
      const session = await this.sessionStore.get(sessionId);

      return {
        role_slot: roleSlot,
        status: "ACTIVE",
        active_generation: binding.active_generation,
        active_session_id: binding.active_session_id,
        locator: session.locator,
        surface: session.surface,
        bootstrapped: true,
      };
    }
  }

  /**
   * Sends a CLOUD_ROLE_REQUEST to the active generation of a role slot.
   */
  async sendRole(params) {
    const {
      roleSlot,
      taskPrompt,
      purpose,
      candidateSha,
      issue = "3",
      pr = "4",
      repository = "tosumitdhaka/agent-control-plane",
      requestId,
    } = params;

    this.requireExistingCdp();

    const def = ROLE_SLOT_DEFINITIONS[roleSlot];
    const roleName = def?.logicalRole ?? roleSlot;

    // Verify active binding first
    const active = await this.lifecycleManager.getActiveBinding(roleSlot);

    // Format envelope
    const envelope = createRequestEnvelope({
      role: roleName,
      repository,
      issue,
      pr,
      candidateSha,
      purpose,
      taskPrompt:
        `${taskPrompt.trim()}\n\n` +
        "Return one CLOUD_ROLE_RESULT v1 envelope for this request. Do not include progress narration or exposed reasoning; provide concise findings in the envelope body.",
      requestId,
    });

    // Deliver via lifecycle manager
    const receipt = await this.lifecycleManager.sendRoleMessage(roleSlot, envelope.rawText, envelope.requestId);

    // Persist pending request record in gitignored state
    const requestRecord = {
      role_slot: roleSlot,
      role: roleName,
      request_id: envelope.requestId,
      generation: active.active_generation,
      session_id: active.active_session_id,
      candidate_sha: candidateSha,
      purpose,
      delivered_at: receipt.delivered_at,
      locator: receipt.locator,
    };

    await this.recordRequest(requestRecord);

    return {
      receipt,
      envelope,
      request_record: requestRecord,
    };
  }

  /**
   * Waits for and retrieves the assistant response corresponding to a request_id.
   */
  async waitRoleResponse(params) {
    const {
      roleSlot,
      timeoutMs = 120_000,
      expectedSha,
    } = params;

    this.requireExistingCdp();

    let requestId = params.requestId;
    if (!requestId) {
      const lastReq = await this.readLastRequest(roleSlot);
      if (!lastReq || !lastReq.request_id) {
        throw new SessionHostError(
          "ROUTER_DELIVERY_FAILED",
          `No pending request found for role_slot="${roleSlot}". Provide --request-id explicitly.`
        );
      }
      requestId = lastReq.request_id;
    }

    const requestRecord = await this.readRequest(requestId);
    if (
      requestRecord.role_slot !== roleSlot ||
      requestRecord.generation === undefined ||
      requestRecord.session_id === undefined
    ) {
      throw new SessionHostError(
        "ROUTER_DELIVERY_FAILED",
        `Request "${requestId}" is not recorded for role_slot="${roleSlot}".`,
      );
    }
    if (expectedSha && expectedSha.toLowerCase() !== requestRecord.candidate_sha.toLowerCase()) {
      throw new SessionHostError(
        "ROUTER_DELIVERY_FAILED",
        "The requested SHA does not match the SHA recorded for this request.",
      );
    }
    const candidateSha = expectedSha ?? requestRecord.candidate_sha;

    // Step 1: Resolve active generation
    const active = await this.lifecycleManager.getActiveBinding(roleSlot);
    if (
      active.active_generation !== requestRecord.generation ||
      active.active_session_id !== requestRecord.session_id
    ) {
      throw new SessionHostError(
        "STALE_SESSION_GENERATION",
        "The request belongs to a role generation that is no longer active.",
      );
    }
    const sessionMetadata = await this.sessionStore.get(active.active_session_id);

    if (sessionMetadata.surface !== "CHAT") {
      throw new SessionHostError(
        "FORBIDDEN_SURFACE",
        `Stored session for role_slot="${roleSlot}" has non-CHAT surface: ${sessionMetadata.surface}`
      );
    }

    const locator = validateChatGptLocator(sessionMetadata.locator);
    if (!isCanonicalConversationUrl(locator)) {
      throw new SessionHostError(
        "LOCATOR_NOT_CAPTURED",
        "Stored locator is not a canonical conversation locator."
      );
    }

    // Step 2: Acquire browser session via proven Strategy
    // Strategy handles profile authority verification, CDP loopback validation, etc.
    const browserSession = await this.strategy["acquireBrowserSession"](
      sessionMetadata.profile_id
    );
    let page;

    try {
      page = await browserSession.context.newPage();
      await page.goto(locator, { waitUntil: "domcontentloaded" });

      // Step 3: Require ready conversation & verify surface
      await this.strategy["requireReadyConversation"](browserSession.context, page);

      const reopened = validateChatGptLocator(page.url());
      if (reopened !== locator || !isCanonicalConversationUrl(reopened)) {
        throw new SessionHostError(
          "LOCATOR_NOT_CAPTURED",
          "Stored locator did not reopen the same canonical ChatGPT URL."
        );
      }

      if (sessionMetadata.project_locator !== null) {
        await requirePositiveProjectAuthority(page, sessionMetadata.project_locator, 10_000);
      }

      // Re-verify that generation has not advanced while connecting
      const recheckedActive = await this.lifecycleManager.getActiveBinding(roleSlot);
      if (
        recheckedActive.active_generation !== active.active_generation ||
        recheckedActive.active_session_id !== active.active_session_id
      ) {
        throw new SessionHostError(
          "STALE_SESSION_GENERATION",
          `Active role generation advanced from ${active.active_generation} to ${recheckedActive.active_generation}.`
        );
      }

      // Step 4: Observe visible transcript for the assistant reply
      const observed = await observeAssistantResponse(page, {
        requestId,
        timeoutMs,
      });

      // Step 5: Parse and validate result envelope
      const def = ROLE_SLOT_DEFINITIONS[roleSlot];
      const parsed = parseResultEnvelope(observed.text);

      const validated = validateResultEnvelope(parsed, {
        requestId,
        role: def?.logicalRole ?? roleSlot,
        candidateSha,
        expectedGeneration: active.active_generation,
        currentActiveGeneration: recheckedActive.active_generation,
      });

      const responseRecord = {
        role_slot: roleSlot,
        generation: active.active_generation,
        session_id: active.active_session_id,
        locator,
        request_id: validated.requestId,
        role: validated.role,
        reviewed_sha: validated.reviewedSha,
        status: validated.status,
        body: validated.body,
        observed_at: observed.finishedAt,
      };

      await this.recordResponse(responseRecord);

      return responseRecord;
    } finally {
      await page?.close().catch(() => {});
      await browserSession.close();
    }
  }

  /**
   * Replaces an active generation with CAS.
   */
  async replaceRole(params) {
    const {
      roleSlot,
      expectedGeneration,
      newSessionId,
      profileId = "default",
      bootstrapMessage,
      bootstrapFile,
      projectLocator,
    } = params;

    this.requireExistingCdp();

    const current = await this.lifecycleManager.getActiveBinding(roleSlot);
    const currentMetadata = await this.sessionStore.get(current.active_session_id);
    const resolvedProjectLocator =
      validateProjectLocator(projectLocator ?? currentMetadata.project_locator) ?? null;
    if (!resolvedProjectLocator) {
      throw new SessionHostError("PROJECT_UNVERIFIED", "Role replacement requires an explicit or currently bound Project.");
    }

    let resolvedBootstrap = bootstrapMessage;
    if (!resolvedBootstrap && bootstrapFile) {
      resolvedBootstrap = await readFile(resolve(bootstrapFile), "utf8");
    }
    if (!resolvedBootstrap) {
      const def = ROLE_SLOT_DEFINITIONS[roleSlot];
      if (def) {
        const resourcePath = resolve(
          dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")),
          "..",
          "resources",
          def.bootstrapFile
        );
        resolvedBootstrap = await readFile(resourcePath, "utf8");
      }
    }

    if (!resolvedBootstrap) {
      throw new SessionHostError(
        "BOOTSTRAP_DELIVERY_FAILED",
        "Bootstrap message is required for role replacement."
      );
    }

    const result = await this.lifecycleManager.replaceRoleSlot({
      roleSlot,
      expectedGeneration,
      newSessionId: newSessionId ?? `${roleSlot}-gen${expectedGeneration + 1}-${Date.now().toString(36)}`,
      profileId,
      bootstrapMessage: resolvedBootstrap,
      projectLocator: resolvedProjectLocator,
    });

    return result;
  }

  async createChat(params) {
    this.requireExistingCdp();
    const { sessionId, projectLocator, bootstrapMessage, profileId = "default" } = params;
    if (!/^[A-Za-z0-9._-]+$/.test(sessionId ?? "") || [".", "..", "constructor", "prototype", "__proto__"].includes(sessionId)) {
      throw new SessionHostError("LOCATOR_NOT_CAPTURED", "A safe --session identifier is required.");
    }
    const project = validateProjectLocator(projectLocator);
    if (!project) {
      throw new SessionHostError("PROJECT_UNVERIFIED", "Chat creation requires an explicit --project locator.");
    }
    const metadata = await this.adapter.create({
      session_id: sessionId,
      profile_id: profileId,
      bootstrap_message: bootstrapMessage,
      project_locator: project,
    });
    return { session_id: sessionId, ...metadata };
  }

  async renameChat(params) {
    this.requireExistingCdp();
    const { sessionId, title, expectedLocator } = params;
    const metadata = await this.sessionStore.get(sessionId);
    const expected = validateChatGptLocator(expectedLocator);
    if (!expected || expected !== metadata.locator || !metadata.project_locator) {
      throw new SessionHostError("LOCATOR_NOT_CAPTURED", "Rename requires the exact stored Project conversation locator.");
    }
    const renamedTitle = await this.adapter.rename(sessionId, title);
    return { session_id: sessionId, locator: metadata.locator, title: renamedTitle };
  }

  async deleteChat(params) {
    this.requireExistingCdp();
    const { sessionId, title, expectedLocator } = params;
    if (!sessionId?.startsWith("bridge-validation-")) {
      throw new SessionHostError(
        "STALE_SESSION_GENERATION",
        "Only an explicitly created bridge-validation-* chat may be deleted by this CLI.",
      );
    }
    const expected = validateChatGptLocator(expectedLocator);
    return this.lifecycleStore.withLock(async () => {
      if (await this.lifecycleStore.isActiveSession(sessionId)) {
        throw new SessionHostError(
          "STALE_SESSION_GENERATION",
          "An active role session cannot be deleted.",
        );
      }
      const metadata = await this.sessionStore.get(sessionId);
      if (!expected || expected !== metadata.locator || !metadata.project_locator) {
        throw new SessionHostError(
          "LOCATOR_NOT_CAPTURED",
          "Deletion requires the exact stored Project conversation locator.",
        );
      }
      await this.adapter.delete(sessionId, title);
      return { session_id: sessionId, deleted: true };
    });
  }

  requireExistingCdp() {
    if (!this.cdpEndpoint) {
      throw new SessionHostError(
        "BROWSER_UNAVAILABLE",
        "This skill only attaches to an already-running browser; provide --cdp-endpoint. Browser launch is disabled.",
      );
    }
  }

  // --- Internal Gitignored Bridge State Helpers ---

  async recordRequest(record) {
    const dir = resolve(this.bridgeStateDir, "requests");
    await mkdir(dir, { recursive: true });
    await writeFile(
      resolve(dir, `${record.request_id}.json`),
      JSON.stringify(record, null, 2),
      "utf8"
    );

    const rolesDir = resolve(this.bridgeStateDir, "roles");
    await mkdir(rolesDir, { recursive: true });
    await writeFile(
      resolve(rolesDir, `${record.role_slot}-last-request.json`),
      JSON.stringify(record, null, 2),
      "utf8"
    );
  }

  async readLastRequest(roleSlot) {
    try {
      const filePath = resolve(this.bridgeStateDir, "roles", `${roleSlot}-last-request.json`);
      const content = await readFile(filePath, "utf8");
      return JSON.parse(content);
    } catch {
      return null;
    }
  }

  async readRequest(requestId) {
    try {
      const filePath = resolve(this.bridgeStateDir, "requests", `${requestId}.json`);
      return JSON.parse(await readFile(filePath, "utf8"));
    } catch {
      throw new SessionHostError(
        "ROUTER_DELIVERY_FAILED",
        `No saved request record exists for request_id="${requestId}".`,
      );
    }
  }

  async recordResponse(record) {
    const dir = resolve(this.bridgeStateDir, "responses");
    await mkdir(dir, { recursive: true });
    await writeFile(
      resolve(dir, `${record.request_id}.json`),
      JSON.stringify(record, null, 2),
      "utf8"
    );
  }
}
