import { existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

function resolveAcpRoot() {
  const candidates = [
    process.env.ACP_ROOT,
    resolve(__dirname, "../../../../"), // When running inside ACP/.agents/skills/chatgpt-role-bridge/scripts
    resolve(__dirname, "../../../../../agent-control-plane"), // Sibling directory when running inside Skills/skills/projects/chatgpt-role-bridge/scripts
    "E:/Projects/agent-control-plane",
    "C:/Projects/agent-control-plane",
  ].filter(Boolean);

  for (const cand of candidates) {
    if (existsSync(resolve(cand, "dist/packages/session-host/src/adapter.js"))) {
      return cand;
    }
  }
  return null;
}

const acpRoot = resolveAcpRoot();

let ChatGptBrowserStrategy;
let LocalSessionStore;
let LifecycleStore;
let LifecycleManager;
let ChatGptSessionAdapter;
let SessionHostError;
let asSessionHostError;
let SESSION_ERROR_CODES;
let isCanonicalConversationUrl;
let validateChatGptLocator;
let validateProjectLocator;
let requirePositiveProjectAuthority;

if (acpRoot) {
  const stratMod = await import(pathToFileURL(resolve(acpRoot, "dist/packages/session-host/src/chatgpt/browser-strategy.js")).href);
  ChatGptBrowserStrategy = stratMod.ChatGptBrowserStrategy;

  const storeMod = await import(pathToFileURL(resolve(acpRoot, "dist/packages/session-host/src/storage/local-session-store.js")).href);
  LocalSessionStore = storeMod.LocalSessionStore;

  const lcStoreMod = await import(pathToFileURL(resolve(acpRoot, "dist/packages/session-host/src/lifecycle/lifecycle-store.js")).href);
  LifecycleStore = lcStoreMod.LifecycleStore;

  const lcMgrMod = await import(pathToFileURL(resolve(acpRoot, "dist/packages/session-host/src/lifecycle/lifecycle-manager.js")).href);
  LifecycleManager = lcMgrMod.LifecycleManager;

  const adapterMod = await import(pathToFileURL(resolve(acpRoot, "dist/packages/session-host/src/adapter.js")).href);
  ChatGptSessionAdapter = adapterMod.ChatGptSessionAdapter;

  const errMod = await import(pathToFileURL(resolve(acpRoot, "dist/packages/protocol/src/errors.js")).href);
  SessionHostError = errMod.SessionHostError;
  asSessionHostError = errMod.asSessionHostError;
  SESSION_ERROR_CODES = errMod.SESSION_ERROR_CODES;

  const locMod = await import(pathToFileURL(resolve(acpRoot, "dist/packages/session-host/src/chatgpt/locator.js")).href);
  isCanonicalConversationUrl = locMod.isCanonicalConversationUrl;
  validateChatGptLocator = locMod.validateChatGptLocator;
  validateProjectLocator = locMod.validateProjectLocator;

  const detMod = await import(pathToFileURL(resolve(acpRoot, "dist/packages/session-host/src/chatgpt/project-detector.js")).href);
  requirePositiveProjectAuthority = detMod.requirePositiveProjectAuthority;
} else {
  // Safe standalone fallback when ACP is not available
  SessionHostError = class extends Error {
    constructor(code, message, options) {
      super(message, options?.cause === undefined ? undefined : { cause: options.cause });
      this.name = "SessionHostError";
      this.code = code;
      this.details = options?.details;
    }
  };
  asSessionHostError = function(error, fallbackCode, fallbackMessage) {
    if (error instanceof SessionHostError) return error;
    return new SessionHostError(fallbackCode, fallbackMessage, { cause: error });
  };
  SESSION_ERROR_CODES = [
    "AUTH_REQUIRED", "BROWSER_UNAVAILABLE", "BROWSER_UNSUPPORTED", "PROJECT_UNVERIFIED",
    "SURFACE_UNVERIFIED", "FORBIDDEN_SURFACE", "CHAT_CREATION_FAILED", "LOCATOR_NOT_CAPTURED",
    "BOOTSTRAP_DELIVERY_FAILED", "ROUTER_DELIVERY_FAILED", "PROVIDER_UI_CHANGED",
    "STALE_SESSION_GENERATION", "DELIVERY_AMBIGUOUS", "IDEMPOTENCY_CONFLICT",
    "DELIVERY_DURABILITY_UNAVAILABLE"
  ];
  ChatGptBrowserStrategy = class {};
  LocalSessionStore = class {};
  LifecycleStore = class {};
  LifecycleManager = class {};
  ChatGptSessionAdapter = class {};
  isCanonicalConversationUrl = (url) => typeof url === "string" && url.includes("/c/");
  validateChatGptLocator = (loc) => loc;
  validateProjectLocator = (loc) => loc;
  requirePositiveProjectAuthority = async () => true;
}

export {
  ChatGptBrowserStrategy,
  LocalSessionStore,
  LifecycleStore,
  LifecycleManager,
  ChatGptSessionAdapter,
  SessionHostError,
  asSessionHostError,
  SESSION_ERROR_CODES,
  isCanonicalConversationUrl,
  validateChatGptLocator,
  validateProjectLocator,
  requirePositiveProjectAuthority,
};
