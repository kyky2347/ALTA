import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import process from "node:process";

function assertOwnerOnly(metadata, description) {
  if (process.platform === "win32") return;
  if ((metadata.mode & 0o077) !== 0)
    throw new Error(`${description} must be owner-only`);
  if (typeof process.getuid === "function" && metadata.uid !== process.getuid())
    throw new Error(`${description} must be owned by the current user`);
}

export function externalCredentialRoot(env = process.env) {
  if (env.ALTA_CREDENTIALS_DIR) {
    if (!path.isAbsolute(env.ALTA_CREDENTIALS_DIR))
      throw new Error("ALTA_CREDENTIALS_DIR must be an absolute path");
    return env.ALTA_CREDENTIALS_DIR;
  }
  const configHome = env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config");
  return path.join(configHome, "alta", "credentials");
}

function credentialDirectory(root, directoryName, { create = false } = {}) {
  const directoryPath = path.join(root, directoryName);
  if (!fs.existsSync(directoryPath)) {
    if (!create) return null;
    fs.mkdirSync(directoryPath, { recursive: true, mode: 0o700 });
  }
  const directory = fs.lstatSync(directoryPath);
  if (directory.isSymbolicLink() || !directory.isDirectory())
    throw new Error(
      `ALTA ${directoryName} credential path must be a real directory`,
    );
  assertOwnerOnly(directory, `ALTA ${directoryName} credential directory`);
  fs.chmodSync(directoryPath, 0o700);
  return directoryPath;
}

export function findCredentialFiles(root, directoryName, hints) {
  const directoryPath = credentialDirectory(root, directoryName);
  if (!directoryPath) return [];

  const matches = [];
  const entries = fs
    .readdirSync(directoryPath, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name));
  for (const entry of entries) {
    if (entry.name.startsWith(".")) continue;
    if (entry.isSymbolicLink())
      throw new Error("ALTA credential files must not be symbolic links");
    if (!entry.isFile()) continue;
    const file = path.join(directoryPath, entry.name);
    const metadata = fs.lstatSync(file);
    if (metadata.isSymbolicLink() || !metadata.isFile())
      throw new Error("ALTA credential files must be regular files");
    if (process.platform !== "win32" && (metadata.mode & 0o077) !== 0)
      throw new Error("ALTA credential files must be owner-only regular files");
    assertOwnerOnly(metadata, "ALTA credential files");
    if (hints.some((hint) => entry.name.toLowerCase().includes(hint)))
      matches.push(file);
  }
  return matches;
}

export function findCredentialFile(root, directoryName, hints) {
  const matches = findCredentialFiles(root, directoryName, hints);
  if (matches.length > 1)
    throw new Error(
      `Multiple ALTA ${directoryName} credential files match ${hints.join("/")}; keep exactly one`,
    );
  return matches[0] ?? null;
}

export function readCredentialText(file) {
  if (fs.statSync(file).size > 64 * 1024)
    throw new Error("ALTA credential files must not exceed 64 KiB");
  return fs.readFileSync(file, "utf8");
}

function syncDirectory(directoryPath) {
  if (process.platform === "win32") return;
  const descriptor = fs.openSync(directoryPath, "r");
  try {
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
}

function atomicCredentialWrite(directoryPath, file, value, suffix = "tmp") {
  const temporary = path.join(
    directoryPath,
    `.${path.basename(file)}.${randomUUID()}.${suffix}`,
  );
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, value);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    fs.renameSync(temporary, file);
    fs.chmodSync(file, 0o600);
    syncDirectory(directoryPath);
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    try {
      fs.unlinkSync(temporary);
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
}

export function replaceCredentialFile({
  root,
  directoryName,
  hints,
  canonicalName,
  value,
}) {
  const directoryPath = credentialDirectory(root, directoryName, {
    create: true,
  });
  const existing = findCredentialFile(root, directoryName, hints);
  const file = existing ?? path.join(directoryPath, canonicalName);
  if (fs.existsSync(file)) {
    const metadata = fs.lstatSync(file);
    if (metadata.isSymbolicLink() || !metadata.isFile())
      throw new Error("ALTA credential target must be a regular file");
    assertOwnerOnly(metadata, "ALTA credential target");
  }
  const previous = fs.existsSync(file) ? fs.readFileSync(file) : null;
  atomicCredentialWrite(directoryPath, file, `${value}\n`);
  return {
    file,
    restore() {
      if (previous === null) {
        fs.unlinkSync(file);
        syncDirectory(directoryPath);
        return;
      }
      atomicCredentialWrite(directoryPath, file, previous, "rollback");
    },
  };
}
