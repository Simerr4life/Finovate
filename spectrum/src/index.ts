import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import { terminal } from "spectrum-ts/providers/terminal";

/**
 * Finovate Spectrum adapter.
 *
 * Receives iMessage (and optional terminal) traffic through Spectrum,
 * asks Django's assistant brain for a reply, then delivers that reply
 * over the same channel. Django never sends iMessage itself.
 *
 * Env:
 *   PROJECT_ID / PROJECT_SECRET — Photon Spectrum Cloud credentials
 *   FINOVATE_URL — Django origin (default http://127.0.0.1:8000)
 *   ASSISTANT_BRIDGE_SECRET — must match Django's ASSISTANT_BRIDGE_SECRET
 *     (or IMESSAGE_PROJECT_SECRET). Defaults to PROJECT_SECRET.
 *   SPECTRUM_PROVIDERS — "imessage", "terminal", or "imessage,terminal"
 */

const finovateUrl = (process.env.FINOVATE_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);
const bridgeSecret =
  process.env.ASSISTANT_BRIDGE_SECRET || process.env.PROJECT_SECRET || "";

type BridgeResponse = {
  ok?: boolean;
  duplicate?: boolean;
  reply?: string;
  linked?: boolean;
  error?: string;
};

async function askFinovate(
  chatId: string,
  text: string,
  messageId: string,
): Promise<BridgeResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (bridgeSecret) {
    headers["X-Finovate-Bridge-Secret"] = bridgeSecret;
  }

  const response = await fetch(`${finovateUrl}/assistant/bridge/`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      chat_id: chatId,
      text,
      message_id: messageId,
      delivery_id: "spectrum-node",
    }),
  });

  let body: BridgeResponse = {};
  try {
    body = (await response.json()) as BridgeResponse;
  } catch {
    body = { error: "invalid_json" };
  }

  if (!response.ok) {
    throw new Error(
      `Finovate bridge HTTP ${response.status}: ${body.error || response.statusText}`,
    );
  }
  return body;
}

function selectedProviders() {
  const raw = (process.env.SPECTRUM_PROVIDERS || "imessage").toLowerCase();
  const names = new Set(
    raw
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean),
  );
  const providers = [];
  if (names.has("imessage")) {
    providers.push(imessage.config());
  }
  if (names.has("terminal")) {
    providers.push(terminal.config());
  }
  if (providers.length === 0) {
    providers.push(terminal.config());
  }
  return providers;
}

const projectId = process.env.PROJECT_ID || process.env.IMESSAGE_PROJECT_ID;
const projectSecret =
  process.env.PROJECT_SECRET || process.env.IMESSAGE_PROJECT_SECRET;
const providers = selectedProviders();

const app =
  projectId && projectSecret
    ? await Spectrum({ projectId, projectSecret, providers })
    : await Spectrum({ providers });

console.log(
  `Finovate Spectrum adapter ready → ${finovateUrl}/assistant/bridge/`,
);

for await (const [space, message] of app.messages) {
  if (message.direction === "outbound") continue;
  if (message.content.type !== "text") continue;

  const text = message.content.text?.trim() ?? "";
  if (!text) continue;

  try {
    await message.react("👍");
  } catch {
    // Tapbacks are best-effort; terminal and some lines may not support them.
  }

  try {
    await space.responding(async () => {
      const result = await askFinovate(space.id, text, message.id);
      if (result.duplicate || !result.reply) return;
      await message.reply(result.reply);
    });
  } catch (error) {
    console.error("Finovate bridge failed", error);
    try {
      await message.reply(
        "Finovate couldn't process that message just now. Try again in a moment.",
      );
    } catch {
      // Ignore secondary send failures.
    }
  }
}
