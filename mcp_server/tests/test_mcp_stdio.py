"""The gridprint-engine MCP server over stdio: tool list and one real tool call on a tiny synthetic clip."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from eval.simulator.render import SimConfig, simulate
from mcp_server.tools import TOOL_NAMES

REPO = Path(__file__).resolve().parents[2]


def test_stdio_tools_and_probe(tmp_path: Path) -> None:
    simulate(SimConfig(duration_s=2.0, width=96, height=64, ref_margin_s=10), tmp_path, "tiny")
    jobs = tmp_path / "jobs"
    (jobs / "j1").mkdir(parents=True)
    (jobs / "j1" / "job.json").write_text(json.dumps({"video": str(tmp_path / "tiny.mp4"), "claim": {}}))
    env = {**os.environ, "GRIDPRINT_WORKDIR": str(jobs), "GRIDPRINT_GRIDLOG": str(tmp_path / "gridlog" / "tiny"),
           "GRIDPRINT_STORE": str(tmp_path / "store"), "PYTHONPATH": f"{REPO}{os.pathsep}{REPO / 'engine'}"}

    async def go() -> tuple[set[str], dict]:
        params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], env=env,
                                       cwd=str(REPO))
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            res = await s.call_tool("probe_video", {"job_id": "j1"})
            return names, json.loads(res.content[0].text)

    names, probe = asyncio.run(go())
    assert names == set(TOOL_NAMES)
    assert probe["metadata"]["frames"] == 60 and probe["hdr"] is False
