import { randomBytes } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

function authMode(value) {
  const mode = String(value ?? "official")
    .trim()
    .toLowerCase();
  if (["official", "shared"].includes(mode)) return "official";
  if (["isolated", "private"].includes(mode)) return "isolated";
  throw new Error("ALTA_OPENAI_AUTH_MODE must be official or isolated");
}

function lstat(file) {
  try {
    return fs.lstatSync(file);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

function sameFile(left, right) {
  try {
    const leftStat = fs.statSync(left);
    const rightStat = fs.statSync(right);
    return leftStat.dev === rightStat.dev && leftStat.ino === rightStat.ino;
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

function referencesSource(destination, source) {
  const destinationStat = lstat(destination);
  if (!destinationStat) return false;
  if (!destinationStat.isSymbolicLink()) return sameFile(destination, source);
  const target = fs.readlinkSync(destination);
  return (
    path.resolve(path.dirname(destination), target) === path.resolve(source)
  );
}

function replacePath(temporary, destination) {
  try {
    fs.renameSync(temporary, destination);
    return;
  } catch (error) {
    if (!lstat(destination) || !["EEXIST", "EPERM"].includes(error.code))
      throw error;
  }

  const backup = `${destination}.${randomBytes(8).toString("hex")}.backup`;
  fs.renameSync(destination, backup);
  try {
    fs.renameSync(temporary, destination);
    fs.rmSync(backup, { force: true });
  } catch (error) {
    if (!lstat(destination)) fs.renameSync(backup, destination);
    throw error;
  }
}

function installOfficialReference(source, destination) {
  if (referencesSource(destination, source))
    return lstat(destination).isSymbolicLink() ? "symbolic link" : "hard link";

  fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
  const temporary = `${destination}.${randomBytes(8).toString("hex")}.tmp`;
  let kind = "symbolic link";
  try {
    try {
      fs.symlinkSync(source, temporary, "file");
    } catch (error) {
      if (
        process.platform !== "win32" ||
        !["EACCES", "EPERM", "UNKNOWN"].includes(error.code)
      )
        throw error;
      fs.linkSync(source, temporary);
      kind = "hard link";
    }
    replacePath(temporary, destination);
    return kind;
  } finally {
    fs.rmSync(temporary, { force: true });
  }
}

function installIsolatedCopy(source, destination) {
  const destinationStat = lstat(destination);
  if (destinationStat && !referencesSource(destination, source)) return false;
  if (!fs.existsSync(source)) {
    if (destinationStat?.isSymbolicLink()) fs.unlinkSync(destination);
    return false;
  }

  fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
  const temporary = `${destination}.${randomBytes(8).toString("hex")}.tmp`;
  try {
    fs.copyFileSync(source, temporary, fs.constants.COPYFILE_EXCL);
    fs.chmodSync(temporary, 0o600);
    replacePath(temporary, destination);
    return true;
  } finally {
    fs.rmSync(temporary, { force: true });
  }
}

/**
 * Selects the OpenAI credential source without moving ALTA's other state out of
 * its project-local CODEX_HOME. Official mode shares one rotating credential
 * file so Codex refresh-token rotation cannot leave ALTA with a stale copy.
 */
export function configureOpenAiAuth({
  officialAuthFile,
  altaAuthFile,
  mode = process.env.ALTA_OPENAI_AUTH_MODE,
}) {
  const selected = authMode(mode);
  if (selected === "official") {
    const reference = installOfficialReference(officialAuthFile, altaAuthFile);
    return {
      mode: selected,
      available: fs.existsSync(officialAuthFile),
      reference,
      source: officialAuthFile,
    };
  }

  const copied = installIsolatedCopy(officialAuthFile, altaAuthFile);
  return {
    mode: selected,
    available: fs.existsSync(altaAuthFile),
    reference: copied ? "private copy" : "private file",
    source: altaAuthFile,
  };
}

export function protectOfficialAuthCommand(mode, args) {
  if (authMode(mode) !== "official") return;
  const [command, action] = args;
  if (command === "logout" || (command === "login" && action !== "status"))
    throw new Error(
      "ALTA uses the local official Codex login. Run `codex login` or `codex logout` explicitly; `./alta openai login status` is read-only.",
    );
}
