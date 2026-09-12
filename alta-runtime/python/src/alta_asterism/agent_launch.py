import os
import sys
from collections.abc import Mapping, Sequence

# These provider/tool keys reach only the trusted Node gateway launcher. The
# launcher consumes them, then its agentSafeChildEnvironment strips them before
# starting the Codex App Server that hosts the model turn.
_ALLOWED_KEYS = {
    "APPDATA",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "CODEX_HOME",
    "COMSPEC",
    "BRAVE_SEARCH_API_KEY",
    "FINNHUB_API_KEY",
    "DEEPSEEK_API_KEY",
    "GROK_API_KEY",
    "HOME",
    "LANG",
    "LOCALAPPDATA",
    "JINA_API_KEY",
    "KIMI_API_KEY",
    "MOONSHOT_API_KEY",
    "NO_COLOR",
    "PATH",
    "PATHEXT",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "RUSTUP_HOME",
    "SHELL",
    "ALTA_AGENT_SAFE_APP_SERVER",
    "ALTA_CREDENTIALS_DIR",
    "ALTA_DISTRIBUTION",
    "ALTA_GATEWAY_TOKEN",
    "ALTA_XAI_WEB_SEARCH_ENABLED",
    "ALTA_SEARCH_BACKEND_TIMEOUT_MS",
    "ALTA_WEB_TIMEOUT_MS",
    "ALTA_WEB_TOOL_TIMEOUT_MS",
    "ALTA_SEARXNG_URL",
    "ALTA_SEC_USER_AGENT",
    "CROSSREF_MAILTO",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "USERPROFILE",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "OPENALEX_API_KEY",
    "XAI_API_KEY",
}


def agent_safe_environment(source: Mapping[str, str]) -> dict[str, str]:
    result = {
        key: value
        for key, value in source.items()
        if key in _ALLOWED_KEYS or key.startswith("LC_")
    }
    result["ALTA_AGENT_SAFE_APP_SERVER"] = "1"
    result["ALTA_XAI_WEB_SEARCH_ENABLED"] = "0"
    result["NO_PROXY"] = "127.0.0.1,localhost"
    return result


def exec_agent(command: Sequence[str]) -> None:
    if not command or not command[0]:
        raise ValueError("agent launch command is required")
    os.execvpe(command[0], list(command), agent_safe_environment(os.environ))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--"]:
        args = args[1:]
    exec_agent(args)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
