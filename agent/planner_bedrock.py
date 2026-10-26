"""Planner using Claude on Amazon Bedrock (Converse API with tool use; SPEC 9, V6).

The model sees the history of tool calls with output summaries and picks the next tool. The policies in
`policies.py` still decide what is executed; the model never writes a verdict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.fallback_planner import Step
from agent.policies import ALLOWED_ARGS, Action

PROMPT = Path(__file__).parent / "prompts" / "planner.md"

TOOL_DOCS = {
    "probe_video": "S1/S2 metadata, timing, gaps, HDR flag.",
    "estimate_readout": "S3 readout time. method: auto|sidecar|profile|blind.",
    "analyze_motion": "S4/S5 motion and static mask. strictness: normal|strict.",
    "propose_patches": "S6 ranked light patches. strategy: all|top|coherent|bright.",
    "extract_flicker": "S7/S8 band SNR and track. patch_ids, axis (rows+|rows-|cols+|cols-), nominal_hz (50|60), "
                       "frame_subset (list or 'low_motion').",
    "match_reference": "S9/S10 match track to reference. track_id, zone.",
    "check_continuity": "S11 edit candidates. track_id.",
    "face_region_check": "S12 experimental face check. track_id.",
    "compute_verdict": "S13 deterministic verdict. Last analysis call.",
    "request_user_input": "Ask the user. kind: original_file|camera_model|claimed_time|longer_clip; message.",
    "request_human_review": "Create a review task for CONTRADICTED.",
    "render_report": "Render report. final: bool (false for PENDING_REVIEW).",
}
ARG_SCHEMAS: dict[str, dict[str, Any]] = {
    "method": {"type": "string"}, "strictness": {"type": "string"}, "strategy": {"type": "string"},
    "patch_ids": {"type": "array", "items": {"type": "integer"}}, "axis": {"type": "string"},
    "nominal_hz": {"type": "number"}, "frame_subset": {"type": "string"}, "track_id": {"type": "string"},
    "zone": {"type": "string"}, "kind": {"type": "string"}, "message": {"type": "string"},
    "final": {"type": "boolean"},
}


def tool_config() -> dict[str, Any]:
    tools = []
    for name, doc in TOOL_DOCS.items():
        props = {a: ARG_SCHEMAS[a] for a in sorted(ALLOWED_ARGS[name]) if a in ARG_SCHEMAS}
        tools.append({"toolSpec": {"name": name, "description": doc,
                                   "inputSchema": {"json": {"type": "object", "properties": props}}}})
    tools.append({"toolSpec": {"name": "stop", "description": "Finish the job.",
                               "inputSchema": {"json": {"type": "object", "properties": {}}}}})
    return {"tools": tools, "toolChoice": {"any": {}}}


class BedrockPlanner:
    kind = "bedrock"

    def __init__(self, client: Any, model_id: str, max_tokens: int = 1024):
        self.client = client
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.system = PROMPT.read_text(encoding="utf-8")

    def next_action(self, history: list[Step]) -> Action:
        hist = [{"tool": s.tool, "args": s.args, "result": s.result, "error": s.error} for s in history]
        text = ("Tool history so far (oldest first), as JSON:\n" + json.dumps(hist, default=str)[-60000:]
                + "\nChoose the next tool. Explain your reason in one short sentence before the tool call.")
        resp = self.client.converse(
            modelId=self.model_id, system=[{"text": self.system}],
            messages=[{"role": "user", "content": [{"text": text}]}],
            toolConfig=tool_config(), inferenceConfig={"maxTokens": self.max_tokens})
        reason = ""
        for block in resp["output"]["message"]["content"]:
            if "text" in block:
                reason += block["text"].strip()
            if "toolUse" in block:
                tu = block["toolUse"]
                if tu["name"] == "stop":
                    return Action(None, {}, reason or "planner chose to stop")
                return Action(tu["name"], dict(tu.get("input") or {}), reason or "bedrock planner choice")
        return Action(None, {}, reason or "no tool chosen")


def make_client(profile: str | None, region: str) -> Any:
    import boto3

    return boto3.Session(profile_name=profile, region_name=region).client("bedrock-runtime")
