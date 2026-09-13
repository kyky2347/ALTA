import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** Display-only selection metadata. Never used to authorize an order. */
export function brokerRouteSummary(
  file = path.join(
    os.homedir(),
    ".local/state/alta/brokers/execution-route.json",
  ),
) {
  let fd;
  try {
    fd = fs.openSync(
      file,
      fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK,
    );
    const stat = fs.fstatSync(fd);
    if (
      !stat.isFile() ||
      stat.size > 4096 ||
      stat.nlink !== 1 ||
      stat.mode & 0o077 ||
      stat.uid !== process.getuid()
    )
      throw new Error("invalid_route");
    const value = JSON.parse(fs.readFileSync(fd, "utf8"));
    if (
      value.provider === null &&
      value.binding === null &&
      value.environment === null &&
      value.profile_revision === null
    )
      return { mode: "shadow", provider: null, environment: null };
    if (
      !["tiger", "alpaca", "ibkr", "futu", "longport", "schwab"].includes(
        value.provider,
      ) ||
      !["PAPER", "LIVE"].includes(value.environment) ||
      ![value.binding, value.profile_revision].every(
        (v) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v),
      )
    )
      throw new Error("invalid_route");
    return {
      mode: "broker_api",
      provider: value.provider,
      environment: value.environment,
    };
  } catch (error) {
    return {
      mode: error.code === "ENOENT" ? "shadow" : "unavailable",
      provider: null,
      environment: null,
    };
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}
