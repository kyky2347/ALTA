const REMOTE_ACCESS_ENVIRONMENT = new Set([
  "GIT_ASKPASS",
  "GIT_SSH",
  "GIT_SSH_COMMAND",
  "SSH_AUTH_SOCK",
]);
const REMOTE_ACCESS_PREFIXES = ["GH_", "GITHUB_"];

/**
 * Remove repository credentials from child environments used by research
 * agents. Repository maintenance remains an operator action outside the agent
 * capability boundary.
 */
export function stripRemoteAccessEnvironment(environment) {
  for (const key of Object.keys(environment)) {
    if (
      REMOTE_ACCESS_ENVIRONMENT.has(key) ||
      REMOTE_ACCESS_PREFIXES.some((prefix) => key.startsWith(prefix))
    ) {
      delete environment[key];
    }
  }
  return environment;
}
