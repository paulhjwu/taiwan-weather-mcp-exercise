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

Prereqs:
    pip install openai mcp python-dotenv
    taiwan-weather server running locally:
        cd servers/taiwan-weather && npm run dev
"""
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


def mcp_tools_to_openai(tools) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


async def run_query(query: str) -> None:
    client = OpenAI(base_url=DEEPINFRA_BASE_URL, api_key=DEEPINFRA_API_KEY)

    # installed mcp's type stub declares a 3-tuple, but this version's
    # implementation only yields (read_stream, write_stream)
    async with streamable_http_client(MCP_SERVER_URL) as (read, write):  # type: ignore[misc]
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tools = mcp_tools_to_openai(tools_result.tools)
            print(f"[connected] {len(tools)} tools available", file=sys.stderr)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ]

            while True:
                response = client.chat.completions.create(
                    model=DEEPINFRA_MODEL,
                    messages=messages,
                    tools=tools,
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
                    result = await session.call_tool(tool_call.function.name, args)
                    content = "\n".join(
                        c.text for c in result.content if c.type == "text"
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": content,
                        }
                    )


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "台北市明天會下雨嗎？需要帶傘嗎？"
    asyncio.run(run_query(query))


if __name__ == "__main__":
    main()
