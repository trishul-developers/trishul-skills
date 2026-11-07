import { SessionHostError } from "./acp-loader.mjs";

/**
 * In-browser evaluation function to locate the assistant response corresponding to a request_id.
 * Evaluates document order to ensure only assistant turns that appear AFTER the matching user request turn are considered.
 */
export async function queryAssistantTurn(page, requestId) {
  return page.evaluate((reqId) => {
    function isVisible(element) {
      if (!element) return false;
      if (element.hidden || element.getAttribute("aria-hidden") === "true") return false;
      const style = window.getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) {
        return false;
      }
      return element.offsetWidth > 0 || element.offsetHeight > 0 || element.getClientRects().length > 0;
    }

    const transcript = document.querySelector('main, [role="main"]');
    if (!transcript) {
      return { found: false, reason: "NO_TRANSCRIPT_CONTAINER" };
    }

    // Check if generation / streaming is active in the page
    const stopButtons = Array.from(
      document.querySelectorAll(
        'button[aria-label*="Stop" i], button[data-testid="stop-button"], button[data-testid="fruitjuice-stop-button"]'
      )
    ).filter(isVisible);

    const isStreaming = stopButtons.length > 0;

    // Locate all candidate user turns
    const userSelectors = [
      '[data-message-author-role="user"]',
      '[data-user-message-bubble]',
      '[data-testid="user-message"]',
      'div.bg-user-message',
    ];
    let userElements = [];
    for (const sel of userSelectors) {
      const nodes = Array.from(transcript.querySelectorAll(sel)).filter(isVisible);
      if (nodes.length > 0) {
        userElements = nodes;
        break;
      }
    }

    // Find the user turn that contains the requested request_id
    let matchingUserNode = null;
    for (let i = userElements.length - 1; i >= 0; i--) {
      const el = userElements[i];
      const text = el.innerText || el.textContent || "";
      if (text.includes(`request_id: ${reqId}`) || text.includes(reqId)) {
        matchingUserNode = el;
        break;
      }
    }

    if (!matchingUserNode) {
      return {
        found: false,
        reason: "REQUEST_NOT_IN_TRANSCRIPT",
        userTurnsCount: userElements.length,
      };
    }

    // Locate candidate assistant turns
    const assistantSelectors = [
      '[data-message-author-role="assistant"]',
      '[data-testid*="assistant"]',
      '.agent-turn',
      '[data-testid="bot-message"]',
      // Current ChatGPT renders turns in a labeled "ChatGPT said:" group and
      // no longer exposes the older assistant-role/test-id attributes.
      '[data-chatgpt-selection-conversation-id]',
      'div.group.flex.flex-col',
    ];

    let assistantElements = [];
    for (const sel of assistantSelectors) {
      let nodes = Array.from(transcript.querySelectorAll(sel)).filter(isVisible);
      if (sel === '[data-chatgpt-selection-conversation-id]') {
        // This attribute is present on assistant message bodies; the accessible
        // "ChatGPT said:" heading is a sibling outside this node.
        nodes = nodes.filter((node) =>
          node.hasAttribute('data-chatgpt-selection-message-id'),
        );
      } else if (sel === 'div.group.flex.flex-col') {
        nodes = nodes.filter((node) =>
          /ChatGPT said:/i.test(node.innerText || node.textContent || ""),
        );
      }
      if (nodes.length > 0) {
        assistantElements = nodes;
        break;
      }
    }

    // Find assistant turns that appear AFTER matchingUserNode in document order
    const followingAssistantNodes = assistantElements.filter((asstEl) => {
      const pos = matchingUserNode.compareDocumentPosition(asstEl);
      return Boolean(pos & Node.DOCUMENT_POSITION_FOLLOWING);
    });

    if (followingAssistantNodes.length === 0) {
      return {
        found: true,
        hasAssistantTurn: false,
        isStreaming,
        reason: "WAITING_FOR_ASSISTANT_TURN",
      };
    }

    // Verify there is no subsequent user turn between matchingUserNode and the assistant response
    const subsequentUserNodes = userElements.filter((uEl) => {
      if (uEl === matchingUserNode) return false;
      const pos = matchingUserNode.compareDocumentPosition(uEl);
      return Boolean(pos & Node.DOCUMENT_POSITION_FOLLOWING);
    });

    // We only take the assistant node that corresponds to this user turn (i.e. appears before any subsequent user turn)
    const validTurnAssistantNodes = followingAssistantNodes.filter((asstEl) => {
      for (const nextUser of subsequentUserNodes) {
        const pos = asstEl.compareDocumentPosition(nextUser);
        // If nextUser follows asstEl, then asstEl belongs to our turn.
        // If asstEl follows nextUser, then asstEl belongs to a later user turn!
        if (pos & Node.DOCUMENT_POSITION_PRECEDING) {
          return false;
        }
      }
      return true;
    });

    if (validTurnAssistantNodes.length === 0) {
      return {
        found: false,
        reason: "SUPERSEDED_BY_SUBSEQUENT_USER_TURN",
      };
    }

    // Choose the target assistant turn (latest in this turn block)
    const targetNode = validTurnAssistantNodes[validTurnAssistantNodes.length - 1];
    const rawText = (targetNode.innerText || targetNode.textContent || "")
      .trim()
      .replace(/^ChatGPT said:\s*/i, "");

    return {
      found: true,
      hasAssistantTurn: true,
      isStreaming,
      rawText: rawText.trim(),
    };
  }, requestId);
}

/**
 * Polls for the complete assistant response corresponding to a request_id.
 * Enforces stability to ensure streaming has fully concluded before returning.
 */
export async function observeAssistantResponse(page, options = {}) {
  const {
    requestId,
    timeoutMs = 120_000,
    pollIntervalMs = 500,
    stabilityMs = 1500,
  } = options;

  if (!requestId) {
    throw new SessionHostError(
      "ROUTER_DELIVERY_FAILED",
      "requestId is required to observe an assistant response."
    );
  }

  const deadline = Date.now() + timeoutMs;
  let lastText = "";
  let lastStableTimestamp = 0;
  let lastReason = "NO_RESPONSE";

  while (Date.now() <= deadline) {
    const result = await queryAssistantTurn(page, requestId).catch((err) => ({
      found: false,
      reason: "EVALUATION_ERROR",
      error: String(err),
    }));
    lastReason = result.reason ?? lastReason;

    if (result.found && result.hasAssistantTurn) {
      if (!result.isStreaming && result.rawText.length > 0) {
        if (result.rawText === lastText) {
          if (Date.now() - lastStableTimestamp >= stabilityMs) {
            // Stable and finished
            return {
              requestId,
              text: result.rawText,
              finishedAt: new Date().toISOString(),
            };
          }
        } else {
          lastText = result.rawText;
          lastStableTimestamp = Date.now();
        }
      } else {
        // Still streaming or empty
        lastText = result.rawText;
        lastStableTimestamp = Date.now();
      }
    }

    await page.waitForTimeout(pollIntervalMs);
  }

  throw new SessionHostError(
    "ROUTER_DELIVERY_FAILED",
    `Timed out waiting for assistant response for request_id="${requestId}" after ${timeoutMs}ms (last_observer_state=${lastReason}).`
  );
}
