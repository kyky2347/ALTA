import path from "node:path";
import fs from "node:fs";
import { createHash, createPrivateKey } from "node:crypto";
import {
  externalCredentialRoot,
  replaceCredentialFile,
} from "./credential-files.mjs";
import { acquireLease } from "./storage.mjs";
import { executionMode } from "./execution-mode.mjs";

function reject(code, statusCode = 400) {
  throw Object.assign(new Error(code), { code, statusCode });
}

function canonicalPath(location) {
  try {
    return fs.realpathSync(location);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    try {
      if (fs.lstatSync(location).isSymbolicLink())
        reject("broker_credentials_require_external_storage", 409);
    } catch (metadataError) {
      if (metadataError.code !== "ENOENT") throw metadataError;
    }
    return path.join(
      canonicalPath(path.dirname(location)),
      path.basename(location),
    );
  }
}

export function tigerCredentialText(value) {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.keys(value).sort().join() !== "account,privateKey,tigerId" ||
    typeof value.tigerId !== "string" ||
    typeof value.account !== "string" ||
    !/^\d{4,24}$/.test(value.tigerId ?? "") ||
    !/^\d{17}$/.test(value.account ?? "") ||
    typeof value.privateKey !== "string" ||
    value.privateKey.length > 12000
  )
    reject("tiger_credentials_invalid");
  let key;
  try {
    const raw = value.privateKey
      .trim()
      .replace(/(-----BEGIN [A-Z ]+-----)\s*/, "$1\n")
      .replace(/\s*(-----END [A-Z ]+-----)/, "\n$1");
    key = raw.startsWith("-----BEGIN")
      ? createPrivateKey(raw)
      : createPrivateKey({
          key: Buffer.from(raw, "base64"),
          format: "der",
          type: "pkcs8",
        });
  } catch {
    reject("tiger_private_key_invalid");
  }
  if (
    key.asymmetricKeyType !== "rsa" ||
    (key.asymmetricKeyDetails?.modulusLength ?? 0) < 2048
  )
    reject("tiger_private_key_invalid");
  const encoded = key
    .export({ format: "der", type: "pkcs8" })
    .toString("base64");
  return `tiger_id=${value.tigerId}\naccount=${value.account}\nprivate_key_pk8=${encoded}\n`;
}

/** Write-only, external credential replacement. Never confers trading authority. */
export function replaceTigerCredentials(capital, body, rootDir) {
  let status = capital.status();
  if (
    !body ||
    Object.keys(body).sort().join() !== "credentials,revision" ||
    body.revision !== executionMode(status).revision
  )
    reject("execution_mode_conflict", 409);
  if (status.requestedEnabled || status.authorizationError)
    reject("broker_authority_must_be_disabled", 409);
  const text = tigerCredentialText(body.credentials);
  const env = capital.environment();
  if (env.ALTA_TIGER_CONFIG_PATH) reject("broker_environment_override", 409);
  const root = externalCredentialRoot(env);
  const relative = path.relative(canonicalPath(rootDir), canonicalPath(root));
  if (
    !relative.startsWith(`..${path.sep}`) &&
    relative !== ".." &&
    !path.isAbsolute(relative)
  )
    reject("broker_credentials_require_external_storage", 409);
  const lease = acquireLease(capital.operationLockFile, { busy: "skip" });
  if (!lease) reject("capital_operation_in_progress", 409);
  try {
    status = capital.status();
    if (body.revision !== executionMode(status).revision)
      reject("execution_mode_conflict", 409);
    if (status.requestedEnabled || status.authorizationError)
      reject("broker_authority_must_be_disabled", 409);
    // The same disabled account may rotate an expired key. Changing account
    // needs a proven empty snapshot so an old book cannot be abandoned.
    if (status.configured) {
      const existing = capital.configuration();
      const newAccountHash = createHash("sha256")
        .update(body.credentials.account)
        .digest("hex");
      if (
        existing.accountSha256 !== newAccountHash &&
        (!status.snapshot ||
          status.snapshot.positionCount !== 0 ||
          status.snapshot.openOrderCount !== 0 ||
          !Number.isFinite(Date.parse(status.snapshot.observedAt)) ||
          Date.parse(status.snapshot.observedAt) > Date.now() ||
          Date.now() - Date.parse(status.snapshot.observedAt) > 60000)
      )
        reject("broker_account_change_requires_empty_snapshot", 409);
    }
    const write = replaceCredentialFile({
      root,
      directoryName: "broker",
      hints: ["tiger"],
      canonicalName: "tiger_openapi_config.properties",
      value: text,
    });
    try {
      capital.configuration();
    } catch {
      write.restore();
      reject("tiger_credentials_invalid");
    }
    return capital.status();
  } finally {
    lease.release();
  }
}
