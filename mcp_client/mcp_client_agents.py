#!/usr/bin/env python3
"""
Agentic MCP client for the taiwan-weather MCP server.

Connects to a running taiwan-weather server over MCP Streamable HTTP,
discovers its tools, and runs an LLM tool-use loop (via DeepInfra's
OpenAI-compatible API) to answer one query.

Usage:
    # .env (same directory as this script) holds:
    #   LLM_PROVIDER=DEEPINFRA
    #   DEEPINFRA_MODEL=deepseek-ai/DeepSeek-V4-Flash
    #   DEEPINFRA_BASE_URL=https://api.deepinfra.com/v1/openai
    #   DEEPINFRA_API_KEY=...
    python mcp_client_agents.py "台北市明天會下雨嗎？需要帶傘嗎？"

    # Also print everything sent to / received from the MCP server and LLM:
    python mcp_client_agents.py --show-trace "台北市明天會下雨嗎？需要帶傘嗎？"

Prereqs:
    pip install openai mcp python-dotenv
    taiwan-weather server running locally:
        cd servers/taiwan-weather && npm run dev
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv(Path(__file__).parent / ".env")

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8787/mcp")

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "DEEPINFRA")
if LLM_PROVIDER != "DEEPINFRA":
    raise NotImplementedError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")

DEEPINFRA_MODEL = os.environ["DEEPINFRA_MODEL"]
DEEPINFRA_BASE_URL = os.environ["DEEPINFRA_BASE_URL"]
DEEPINFRA_API_KEY = os.environ["DEEPINFRA_API_KEY"]

SYSTEM_PROMPT = (
    "You are a Taiwan weather assistant. Answer the user's question using "
    "the available weather tools, which query Taiwan's Central Weather "
    "Administration (CWA) open data. Always call a tool rather than "
    "guessing at weather data. Cite the specific city/station in your "
    "final answer. Respond in the same language as the question."
)


def trace(enabled: bool, label: str, payload) -> None:
    """Print a labelled payload (as JSON where possible) to stderr."""
    if not enabled:
        return
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(f"\n[trace] {label}\n{payload}", file=sys.stderr)


def mcp_tools_to_openai(tools) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema,
            },
        }
        for t in tools
    ]


async def run_query(query: str, show_trace: bool = False) -> None:
    client = OpenAI(base_url=DEEPINFRA_BASE_URL, api_key=DEEPINFRA_API_KEY)

    # mcp versions differ: some yield (read, write), newer ones yield
    # (read, write, get_session_id). Only the first two are needed.
    async with streamable_http_client(MCP_SERVER_URL) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            trace(show_trace, "MCP -> server: tools/list", {})
            tools_result = await session.list_tools()
            trace(
                show_trace,
                "MCP <- server: tools/list result",
                tools_result.model_dump(mode="json", exclude_none=True),
            )
            tools = mcp_tools_to_openai(tools_result.tools)
            print(f"[connected] {len(tools)} tools available", file=sys.stderr)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ]

            while True:
                trace(
                    show_trace,
                    f"LLM request -> {DEEPINFRA_MODEL}",
                    {"messages": messages, "tools": [t["function"]["name"] for t in tools]},
                )
                response = client.chat.completions.create(
                    model=DEEPINFRA_MODEL,
                    messages=messages,
                    tools=tools,
                )
                trace(
                    show_trace,
                    "LLM response <-",
                    response.model_dump(mode="json", exclude_none=True),
                )
                message = response.choices[0].message
                messages.append(message.model_dump(exclude_none=True))

                if not message.tool_calls:
                    print(message.content)
                    break

                for tool_call in message.tool_calls:
                    if tool_call.type != "function":
                        continue
                    args = json.loads(tool_call.function.arguments or "{}")
                    print(
                        f"[tool_use] {tool_call.function.name}({args})",
                        file=sys.stderr,
                    )
                    trace(
                        show_trace,
                        "MCP -> server: tools/call",
                        {"name": tool_call.function.name, "arguments": args},
                    )
                    result = await session.call_tool(tool_call.function.name, args)
                    content = "\n".join(
                        c.text for c in result.content if c.type == "text"
                    )
                    trace(
                        show_trace,
                        "MCP <- server: tools/call result",
                        result.model_dump(mode="json", exclude_none=True),
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": content,
                        }
                    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument(
        "query",
        nargs="?",
        default="台北市明天會下雨嗎？需要帶傘嗎？",
        help="question to ask (default: %(default)s)",
    )
    parser.add_argument(
        "--show-trace",
        action="store_true",
        help="print payloads sent to / received from the MCP server and LLM to stderr",
    )
    args = parser.parse_args()
    asyncio.run(run_query(args.query, args.show_trace))


if __name__ == "__main__":
    main()
