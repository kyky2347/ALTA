import process from "node:process";
import {
  CREDENTIAL_SLOT_IDS,
  credentialInventory,
  replaceCredential,
} from "./credential-control.mjs";

async function readStream(stream, maximum = 4_096) {
  const chunks = [];
  let length = 0;
  for await (const chunk of stream) {
    length += chunk.length;
    if (length > maximum) throw new Error("Credential input is too large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8").trim();
}

export async function readCredentialSecret({
  input = process.stdin,
  output = process.stderr,
} = {}) {
  if (!input.isTTY || typeof input.setRawMode !== "function")
    return readStream(input);
  output.write("Credential (input hidden): ");
  input.setRawMode(true);
  input.resume();
  input.setEncoding("utf8");
  let value = "";
  try {
    for await (const chunk of input) {
      for (const character of chunk) {
        if (character === "\r" || character === "\n") {
          output.write("\n");
          return value;
        }
        if (character === "\u0003")
          throw new Error("Credential input cancelled");
        if (character === "\u007f" || character === "\b") {
          value = value.slice(0, -1);
          continue;
        }
        value += character;
        if (value.length > 512)
          throw new Error("Credential input is too large");
      }
    }
  } finally {
    input.setRawMode(false);
    input.pause();
  }
  throw new Error("Credential input ended before a newline");
}

function printInventory(inventory, output = console.log) {
  output("ALTA external credentials");
  output(`  directory: ${inventory.root}`);
  output(`  revision: ${inventory.revision}`);
  for (const item of inventory.slots)
    output(
      `  ${item.slot}: ${item.configured ? `configured (${item.source})` : item.availableWithoutCredential ? "available without credential" : item.credentialRequirement === "optional" ? "optional credential missing" : "missing"}`,
    );
  output(
    `  tiger-paper: ${inventory.trading.configured ? `configured (${inventory.trading.source}); capital runtime disabled` : "not configured; capital runtime disabled"}`,
  );
}

async function reloadActiveService(service) {
  const before = await service.status();
  if (!before.installed || !before.platformActive)
    return { restarted: false, reason: "loaded by the next ALTA process" };
  await service.restart();
  return { restarted: true, reason: "active service restarted and ready" };
}

export async function credentialCommand(
  args,
  {
    service,
    env = process.env,
    readSecret = readCredentialSecret,
    output = console.log,
  },
) {
  const [action = "status", slot, ...extra] = args;
  if (action === "status" || action === "check") {
    if (slot || extra.length)
      throw new Error(`credentials ${action} does not accept arguments`);
    return printInventory(credentialInventory(env), output);
  }
  if (action === "reload") {
    if (slot || extra.length)
      throw new Error("credentials reload does not accept arguments");
    const inventory = credentialInventory(env);
    const result = await reloadActiveService(service);
    output(
      `Credential revision ${inventory.revision}: ${result.reason}. No credential value was logged.`,
    );
    return;
  }
  if (action !== "set")
    throw new Error(
      `Unknown credentials action "${action}"; choose status, check, set, or reload`,
    );
  if (!slot || extra.length)
    throw new Error(
      `Usage: ./alta credentials set <${CREDENTIAL_SLOT_IDS.join("|")}>`,
    );
  const secret = await readSecret();
  const replacement = replaceCredential(slot, secret, env);
  try {
    const result = await reloadActiveService(service);
    output(
      `${replacement.slot} replaced atomically in ${replacement.fileName}; revision ${replacement.revision}; ${result.reason}. No credential value was logged.`,
    );
  } catch (error) {
    replacement.restore();
    try {
      await service.restart();
    } catch {
      throw new Error(
        `${replacement.slot} reload failed and the previous file was restored; service recovery also failed: ${error.message}`,
      );
    }
    throw new Error(
      `${replacement.slot} reload failed; the previous file was restored: ${error.message}`,
    );
  }
}
