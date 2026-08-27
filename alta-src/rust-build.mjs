import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { createHash, randomBytes } from "node:crypto";

import { numberSetting } from "./resource-control.mjs";
import { acquireLease, formatBytes } from "./storage.mjs";
import { executableInPath, runCapture, runProcess } from "./process-runner.mjs";

const GIB = 1024 ** 3;

async function sha256(file) {
  if (!fs.existsSync(file)) return null;
  const hash = createHash("sha256");
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

async function verifyLocalArtifact(file, expected, maxBytes) {
  const stat = await fs.promises.stat(file).catch(() => null);
  if (!stat?.isFile())
    throw new Error(`Required local build artifact is missing: ${file}`);
  if (stat.size <= 0 || stat.size > maxBytes)
    throw new Error(`Local build artifact has an invalid size: ${file}`);
  if ((await sha256(file)) !== expected)
    throw new Error(`Checksum validation failed for ${path.basename(file)}`);
}

export function createRustBuild({
  codeModeHost,
  codexRsDir,
  ensureDirectories,
  isolatedEnvironment,
  runtimeBinary,
  stateDir,
}) {
  const buildBinary = path.join(
    stateDir,
    "target",
    "release",
    process.platform === "win32" ? "codex.exe" : "codex",
  );
  const buildCodeModeHost = path.join(
    stateDir,
    "target",
    "release",
    process.platform === "win32"
      ? "codex-code-mode-host.exe"
      : "codex-code-mode-host",
  );

  function rustChannel() {
    const text = fs.readFileSync(
      path.join(codexRsDir, "rust-toolchain.toml"),
      "utf8",
    );
    return text.match(/channel\s*=\s*"([^"]+)"/)?.[1] ?? "1.95.0";
  }

  function findCargo() {
    const channel = rustChannel();
    const toolchains = path.join(os.homedir(), ".rustup", "toolchains");
    if (fs.existsSync(toolchains)) {
      const match = fs
        .readdirSync(toolchains)
        .sort()
        .find((name) => name === channel || name.startsWith(`${channel}-`));
      if (match) {
        const candidate = path.join(
          toolchains,
          match,
          "bin",
          process.platform === "win32" ? "cargo.exe" : "cargo",
        );
        if (fs.existsSync(candidate)) return candidate;
      }
    }
    return executableInPath(
      process.platform === "win32" ? "cargo.exe" : "cargo",
    );
  }

  async function resolveCodexV8Environment() {
    if (["true", "1", "yes"].includes(process.env.V8_FROM_SOURCE)) return {};
    const archiveOverride = process.env.RUSTY_V8_ARCHIVE;
    const bindingOverride = process.env.RUSTY_V8_SRC_BINDING_PATH;
    if (archiveOverride && bindingOverride) {
      for (const file of [archiveOverride, bindingOverride]) {
        if (
          !path.isAbsolute(file) ||
          !fs.existsSync(file) ||
          !fs.statSync(file).isFile()
        )
          throw new Error(`V8 build override must be an existing local file: ${file}`);
      }
      return {};
    }
    if (archiveOverride || bindingOverride)
      throw new Error(
        "RUSTY_V8_ARCHIVE and RUSTY_V8_SRC_BINDING_PATH must be set together",
      );

    const cargoLock = fs.readFileSync(
      path.join(codexRsDir, "Cargo.lock"),
      "utf8",
    );
    const versions = [
      ...new Set(
        cargoLock
          .split("[[package]]")
          .filter((block) => /^name = "v8"$/m.test(block))
          .map((block) => block.match(/^version = "([^"]+)"$/m)?.[1])
          .filter(Boolean),
      ),
    ];
    if (versions.length !== 1)
      throw new Error(
        `Expected one resolved V8 crate version, found ${versions.length}`,
      );

    const cargo = findCargo();
    const rustc = cargo
      ? path.join(
          path.dirname(cargo),
          process.platform === "win32" ? "rustc.exe" : "rustc",
        )
      : null;
    if (!rustc || !fs.existsSync(rustc))
      throw new Error(
        "rustc was not found next to the selected Cargo executable",
      );
    const rustcVersion = await runCapture(rustc, ["-vV"], {
      env: isolatedEnvironment(),
    });
    const target = rustcVersion.match(/^host: (.+)$/m)?.[1];
    if (!target) throw new Error("Unable to resolve the Rust host target");

    const version = versions[0];
    const profile = "ptrcomp_sandbox_release";
    const cacheDir = process.env.ALTA_RUSTY_V8_CACHE_DIR
      ? path.resolve(process.env.ALTA_RUSTY_V8_CACHE_DIR)
      : path.join(
          stateDir,
          "cache",
          "v8",
          `rusty-v8-${version}-${target}`,
        );
    const archiveName = target.includes("windows")
      ? `rusty_v8_${profile}_${target}.lib.gz`
      : `librusty_v8_${profile}_${target}.a.gz`;
    const bindingName = `src_binding_${profile}_${target}.rs`;
    const checksumsName = `rusty_v8_${profile}_${target}.sha256`;
    const checksums = path.join(cacheDir, checksumsName);
    const checksumText = await fs.promises.readFile(checksums, "utf8").catch(() => {
      throw new Error(
        `Verified local V8 artifacts are required for an ALTA source build. Place ${checksumsName}, ${archiveName}, and ${bindingName} in ${cacheDir}, set ALTA_RUSTY_V8_CACHE_DIR, or provide both RUSTY_V8_ARCHIVE and RUSTY_V8_SRC_BINDING_PATH. The build never downloads them.`,
      );
    });
    if (Buffer.byteLength(checksumText) > 64 * 1024)
      throw new Error("Codex V8 checksum manifest exceeds the local size limit");
    const expected = new Map();
    for (const line of checksumText.trim().split("\n")) {
      const match = line.trim().match(/^([0-9a-f]{64})\s+(.+)$/);
      if (match) expected.set(match[2], match[1]);
    }
    if (!expected.has(archiveName) || !expected.has(bindingName))
      throw new Error("Codex V8 checksum manifest is incomplete");

    const archive = path.join(cacheDir, archiveName);
    const binding = path.join(cacheDir, bindingName);
    await verifyLocalArtifact(
      archive,
      expected.get(archiveName),
      512 * 1024 * 1024,
    );
    await verifyLocalArtifact(
      binding,
      expected.get(bindingName),
      64 * 1024 * 1024,
    );
    return {
      RUSTY_V8_ARCHIVE: archive,
      RUSTY_V8_SRC_BINDING_PATH: binding,
    };
  }

  function installBuiltBinary(source, destination) {
    if (!fs.existsSync(source))
      throw new Error(`Built binary was not found at ${source}`);
    fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
    const temporary = `${destination}.${randomBytes(8).toString("hex")}.tmp`;
    fs.copyFileSync(source, temporary);
    fs.chmodSync(temporary, 0o700);
    if (process.platform === "win32" && fs.existsSync(destination))
      fs.unlinkSync(destination);
    fs.renameSync(temporary, destination);
  }

  function installRuntimeImage() {
    installBuiltBinary(buildBinary, runtimeBinary);
    installBuiltBinary(buildCodeModeHost, codeModeHost);
  }

  function hasBuildOutput() {
    return fs.existsSync(buildBinary) && fs.existsSync(buildCodeModeHost);
  }

  async function build() {
    ensureDirectories();
    const lease = acquireLease(path.join(stateDir, "runtime", "build.lock"));
    const cargo = findCargo();
    try {
      const disk = fs.statfsSync(stateDir);
      const freeBytes = disk.bavail * disk.bsize;
      const minimumFreeBytes =
        numberSetting("ALTA_BUILD_MIN_FREE_GB", 15, 5, 256) * GIB;
      if (freeBytes < minimumFreeBytes)
        throw new Error(
          `ALTA build needs at least ${formatBytes(minimumFreeBytes)} free; only ${formatBytes(freeBytes)} is available`,
        );
      if (!cargo)
        throw new Error(
          `Rust ${rustChannel()} / cargo was not found. Install the toolchain, then rerun ./alta build.`,
        );
      const binDir = path.dirname(cargo);
      console.log("Resolving verified local Codex V8 build artifacts...");
      const codexV8Environment = await resolveCodexV8Environment();
      const env = isolatedEnvironment({
        CARGO_REGISTRIES_CRATES_IO_PROTOCOL: "sparse",
        PATH: `${binDir}${path.delimiter}${process.env.PATH ?? ""}`,
        ...codexV8Environment,
      });
      console.log(
        `Building the isolated ALTA v3.5 binary with Rust ${rustChannel()}...`,
      );
      const code = await runProcess(
        cargo,
        [
          "build",
          "--release",
          "--bin",
          "codex",
          "--bin",
          "codex-code-mode-host",
        ],
        { cwd: codexRsDir, env },
      );
      if (code !== 0 || !hasBuildOutput())
        throw new Error(`cargo build failed with exit code ${code}`);
      installRuntimeImage();
      console.log(`Private runtime image: ${path.dirname(runtimeBinary)}`);
    } finally {
      lease.release();
    }
  }

  return {
    build,
    findCargo,
    hasBuildOutput,
    installRuntimeImage,
  };
}
