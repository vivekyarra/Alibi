"""Agent orchestrator: perception (OpenCV stage outputs) → decision (planner + policies) → action
(MCP tool calls over stdio). SPEC 5, 9."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent import policies
from agent.fallback_planner import FallbackPlanner, Step
from agent.policies import Action, PolicyState
from agent.trace import Trace, now

REPO = Path(__file__).resolve().parents[1]


class Planner(Protocol):
    kind: str
    model_id: str | None

    def next_action(self, history: list[Step]) -> Action: ...


class ToolCaller(Protocol):
    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]: ...


class McpCaller:
    def __init__(self, session: ClientSession):
        self.session = session

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.session.call_tool(tool, args)
        text = "".join(getattr(c, "text", "") for c in res.content)
        if res.isError:
            raise RuntimeError(text or f"{tool} failed")
        return json.loads(text) if text else {}


async def run_job(job_id: str, planner: Planner, caller: ToolCaller, max_iterations: int,
                  max_tool_calls: int, trace_path: Path | None = None) -> tuple[Trace, list[Step]]:
    trace = Trace(job_id)
    history: list[Step] = []
    st = PolicyState(max_iterations=max_iterations, max_tool_calls=max_tool_calls)
    for _ in range(max_tool_calls + 5):
        t0 = now()
        try:
            proposed = planner.next_action(history)
        except Exception as e:  # planner failure (e.g. Bedrock unavailable): fall back for this step
            proposed = FallbackPlanner().next_action(history)
            proposed.reason = f"planner error ({type(e).__name__}); fallback rule: {proposed.reason}"
        action, note = policies.enforce(proposed, st)
        if action.tool is None:
            if proposed.tool is not None or note:
                trace.add(planner.kind, planner.model_id, "(stop)", proposed.args, {}, action.reason, t0, now(),
                          policy_note=note)
            break
        args = dict(action.args)
        if action.tool == "compute_verdict" and st.budget_exhausted:
            args["budget_exhausted"] = True
        call_args = {"job_id": job_id, **{k: v for k, v in args.items() if v is not None}}
        err = None
        result: dict[str, Any] = {}
        try:
            result = await caller.call(action.tool, call_args)
        except Exception as e:
            err = str(e)[:500]
        t1 = now()
        trace.add(planner.kind, planner.model_id, action.tool, call_args, result, action.reason, t0, t1,
                  error=err, policy_note=note)
        history.append(Step(action.tool, args, result if err is None else None, err))
        policies.record(action, result if err is None else None, st)
        if trace_path is not None:
            trace.save(trace_path)
    if trace_path is not None:
        trace.save(trace_path)
    return trace, history


async def run_with_mcp(job_id: str, planner: Planner, max_iterations: int, max_tool_calls: int,
                       env: dict[str, str], trace_path: Path) -> tuple[Trace, list[Step]]:
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"],
                                   env={**os.environ, **env, "PYTHONPATH": f"{REPO}{os.pathsep}{REPO / 'engine'}"},
                                   cwd=str(REPO))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        return await run_job(job_id, planner, McpCaller(session), max_iterations, max_tool_calls, trace_path)


def run_sync(job_id: str, planner: Planner, max_iterations: int, max_tool_calls: int, env: dict[str, str],
             trace_path: Path) -> tuple[Trace, list[Step]]:
    return asyncio.run(run_with_mcp(job_id, planner, max_iterations, max_tool_calls, env, trace_path))


class InProcessCaller:
    """Calls the same tool functions as the MCP server, in this process (evaluation runs many jobs; the
    agent logic and policies are identical, only the transport differs)."""

    def __init__(self, tools: Any):
        self.tools = tools

    async def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        return dict(getattr(self.tools, tool)(**args))


def run_in_process(job_id: str, planner: Planner, tools: Any, max_iterations: int, max_tool_calls: int,
                   trace_path: Path | None) -> tuple[Trace, list[Step]]:
    return asyncio.run(run_job(job_id, planner, InProcessCaller(tools), max_iterations, max_tool_calls, trace_path))
