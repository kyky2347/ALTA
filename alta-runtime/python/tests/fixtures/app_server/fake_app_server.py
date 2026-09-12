import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--delay-scout", default="")
    parser.add_argument("--delay-seconds", type=float, default=0.01)
    parser.add_argument("--ignore-interrupt", action="store_true")
    parser.add_argument("--crash-scout", default="")
    parser.add_argument("--omit-usage-scout", default="")
    parser.add_argument("--empty-first-turn", action="store_true")
    parser.add_argument("--invalid-first-finalization", action="store_true")
    return parser.parse_args()


ARGS = arguments()
RESPONSES = json.loads(ARGS.responses.read_text())
WRITE_LOCK = threading.Lock()
TURN_STATE: dict[str, tuple[str, threading.Event]] = {}
THREAD_COUNT = 0
TURN_COUNT = 0
THREAD_USAGE: dict[str, dict[str, int]] = {}


def write(value: dict) -> None:
    with WRITE_LOCK:
        sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def log_request(message: dict) -> None:
    record = {
        "method": message.get("method"),
        "params": message.get("params"),
        "envKeys": sorted(os.environ),
    }
    with ARGS.log.open("a") as output:
        output.write(json.dumps(record, separators=(",", ":")) + "\n")


def thread_payload(thread_id: str, cwd: str) -> dict:
    now = int(time.time())
    return {
        "cliVersion": "fixture-v1",
        "createdAt": now,
        "cwd": str(Path(cwd).resolve()),
        "ephemeral": True,
        "id": thread_id,
        "modelProvider": "fixture",
        "preview": "",
        "sessionId": thread_id,
        "source": "appServer",
        "status": {"type": "idle"},
        "turns": [],
        "updatedAt": now,
    }


def turn_payload(turn_id: str, status: str) -> dict:
    return {
        "id": turn_id,
        "items": [],
        "status": status,
    }


def scout_id(params: dict) -> str:
    text = params["input"][0]["text"]
    return json.loads(text)["scout_id"]


def complete_turn(thread_id: str, turn_id: str, scout: str, turn_number: int) -> None:
    state = TURN_STATE[turn_id][1]
    delay = ARGS.delay_seconds if scout == ARGS.delay_scout else 0.01
    if state.wait(delay):
        return
    response = RESPONSES[scout]
    tools = response.get("tools", [])
    if ARGS.invalid_first_finalization and turn_number > 1:
        tools = []
    for tool in tools:
        write(
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "completedAtMs": int(time.time() * 1000),
                    "item": {
                        "type": "mcpToolCall",
                        "id": tool["id"],
                        "server": "alta_gateway",
                        "tool": tool["tool"],
                        "arguments": tool["arguments"],
                        "status": "completed",
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Synthetic tool fixture",
                                    "url": tool["source_url"],
                                }
                            ]
                        },
                    },
                },
            }
        )
    output_text = (
        ""
        if ARGS.empty_first_turn and turn_number == 1
        else json.dumps(response["output"], separators=(",", ":"))
    )
    if ARGS.invalid_first_finalization and turn_number == 1:
        output_text = json.dumps(
            {**response["output"], "parent_opportunity_id": "unassigned-parent"}
        )
    write(
        {
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "completedAtMs": int(time.time() * 1000),
                "item": {
                    "type": "agentMessage",
                    "id": f"message_{turn_id}",
                    "phase": "final_answer",
                    "text": output_text,
                },
            },
        }
    )
    usage = {
        "cachedInputTokens": 0,
        "inputTokens": 100,
        "outputTokens": 50,
        "reasoningOutputTokens": 10,
        "totalTokens": 160,
    }
    if scout != ARGS.omit_usage_scout:
        previous = THREAD_USAGE.get(thread_id, {})
        total = {key: value + previous.get(key, 0) for key, value in usage.items()}
        THREAD_USAGE[thread_id] = total
        write(
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "tokenUsage": {
                        "last": usage,
                        "total": total,
                        "modelContextWindow": 10000,
                    },
                },
            }
        )
    write(
        {
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": turn_payload(turn_id, "completed"),
            },
        }
    )


def handle(message: dict) -> None:
    global THREAD_COUNT, TURN_COUNT
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if method == "initialized":
        return
    if method == "initialize":
        write(
            {
                "id": request_id,
                "result": {
                    "userAgent": "fake-app-server/1.0",
                    "serverInfo": {"name": "fake-app-server", "version": "1.0"},
                    "platformFamily": "fixture",
                    "platformOs": "fixture",
                },
            }
        )
        return
    if method == "thread/start":
        THREAD_COUNT += 1
        thread_id = f"thread_{THREAD_COUNT}"
        cwd = params.get("cwd") or os.getcwd()
        write(
            {
                "id": request_id,
                "result": {
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "cwd": str(Path(cwd).resolve()),
                    "instructionSources": [],
                    "model": params.get("model") or "fixture-model",
                    "modelProvider": "fixture",
                    "reasoningEffort": "medium",
                    "sandbox": {"type": "readOnly", "networkAccess": False},
                    "thread": thread_payload(thread_id, cwd),
                },
            }
        )
        return
    if method == "turn/start":
        TURN_COUNT += 1
        turn_id = f"turn_{TURN_COUNT}"
        scout = scout_id(params)
        if scout == ARGS.crash_scout:
            os._exit(17)
        cancellation = threading.Event()
        TURN_STATE[turn_id] = (params["threadId"], cancellation)
        write(
            {
                "id": request_id,
                "result": {"turn": turn_payload(turn_id, "inProgress")},
            }
        )
        threading.Thread(
            target=complete_turn,
            args=(params["threadId"], turn_id, scout, TURN_COUNT),
            daemon=True,
        ).start()
        return
    if method == "turn/interrupt":
        turn_id = params["turnId"]
        thread_id, cancellation = TURN_STATE[turn_id]
        if ARGS.ignore_interrupt:
            write({"id": request_id, "result": {}})
            return
        cancellation.set()
        write({"id": request_id, "result": {}})
        write(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": thread_id,
                    "turn": turn_payload(turn_id, "interrupted"),
                },
            }
        )
        return
    write(
        {
            "id": request_id,
            "error": {"code": -32601, "message": f"unsupported method: {method}"},
        }
    )


for line in sys.stdin:
    message = json.loads(line)
    log_request(message)
    handle(message)
