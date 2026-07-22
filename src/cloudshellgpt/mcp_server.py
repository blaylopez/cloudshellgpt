"""MCP server — exposes CloudShellGPT as Model Context Protocol tools.

This allows CloudShellGPT to be used as a tool from Kiro, Claude Desktop,
Cursor, and other MCP-compatible clients.
"""
from __future__ import annotations

import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from cloudshellgpt.intent import IntentParser
from cloudshellgpt.bedrock_translator import BedrockTranslator
from cloudshellgpt.safety import SafetyLayer
from cloudshellgpt.executor import AWSExecutor


server = Server("cloudshellgpt")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="aws_translate",
            description=(
                "Translate a natural language intent into an AWS CLI command. "
                "Returns the command, explanation, risk level, and estimated cost. "
                "Does NOT execute the command — use aws_execute for that."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Natural language description of what you want to do (any language)",
                    },
                    "region": {
                        "type": "string",
                        "description": "Optional AWS region override",
                    },
                },
                "required": ["intent"],
            },
        ),
        Tool(
            name="aws_execute",
            description=(
                "Execute an AWS CLI command. Returns stdout, stderr, exit code, and duration. "
                "ALWAYS show the user the command before calling this tool — they need to confirm."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The full AWS CLI command to execute",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, add --dry-run flag where supported",
                        "default": False,
                    },
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="aws_cost_preview",
            description=(
                "Estimate the cost of an AWS command before executing it. "
                "Returns breakdown of cost components and warnings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The AWS CLI command to evaluate",
                    },
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="aws_explain",
            description=(
                "Explain what an AWS CLI command does in detail. "
                "Breaks down each flag, describes the operation, and provides docs links."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The AWS CLI command to explain",
                    },
                },
                "required": ["command"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls from MCP clients."""
    try:
        if name == "aws_translate":
            return await _tool_translate(arguments)
        elif name == "aws_execute":
            return await _tool_execute(arguments)
        elif name == "aws_cost_preview":
            return await _tool_cost_preview(arguments)
        elif name == "aws_explain":
            return await _tool_explain(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


async def _tool_translate(args: dict[str, Any]) -> list[TextContent]:
    """Handle aws_translate tool call."""
    intent_text = args.get("intent", "")
    region = args.get("region")

    parser = IntentParser()
    intent = parser.parse(intent_text, region=region)

    translator = BedrockTranslator()
    translation = translator.translate(intent)

    result = {
        "command": translation.command,
        "explanation": translation.explanation,
        "detailed_explanation": translation.detailed_explanation,
        "risk_level": translation.risk_level,
        "estimated_cost": translation.estimated_cost,
        "requires_dry_run": translation.requires_dry_run,
        "affected_resources": translation.affected_resources,
        "flags_used": translation.flags_used,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]


async def _tool_execute(args: dict[str, Any]) -> list[TextContent]:
    """Handle aws_execute tool call."""
    command = args.get("command", "")
    dry_run = args.get("dry_run", False)

    executor = AWSExecutor(dry_run=dry_run)
    result = executor.run(command)

    output = {
        "command": result.command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": result.duration_ms,
        "dry_run": result.dry_run,
    }

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def _tool_cost_preview(args: dict[str, Any]) -> list[TextContent]:
    """Handle aws_cost_preview tool call."""
    # Parse command to identify service and operation
    command = args.get("command", "")

    # Use the safety layer's cost estimation
    # (simplified — full impl would parse command more thoroughly)
    from cloudshellgpt.bedrock_translator import Translation

    mock_translation = Translation(
        command=command,
        explanation="Cost preview",
        detailed_explanation="",
        risk_level="low",
        estimated_cost="TBD",
    )

    safety = SafetyLayer()
    check = safety.assess(mock_translation)

    result = {
        "command": command,
        "estimated_cost": check.estimated_cost,
        "risk_level": check.risk_level,
        "warnings": check.warnings,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _tool_explain(args: dict[str, Any]) -> list[TextContent]:
    """Handle aws_explain tool call."""
    from cloudshellgpt.learning import Explainer

    command = args.get("command", "")
    explainer = Explainer()
    explanation = explainer.explain_sync(command)

    return [TextContent(type="text", text=explanation)]


def serve_mcp() -> None:
    """Run the MCP server on stdio."""
    import asyncio

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())
