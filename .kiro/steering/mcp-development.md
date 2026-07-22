---
inclusion: fileMatch
fileMatchPattern: "**/mcp_server.py"
---

# MCP Server Development — CloudShellGPT

## Overview

CloudShellGPT exposes 4 tools via Model Context Protocol (MCP) for use in Kiro, Claude Desktop, and Cursor.

## Transport

- Uses **stdio** transport (stdin/stdout)
- Started via: `csgpt mcp serve`
- The `mcp` library handles the protocol; we only define tools and handlers

## Tool Definitions

Each tool must have:
- `name`: snake_case identifier
- `description`: clear explanation of what it does and what it does NOT do
- `inputSchema`: JSON Schema object with required/optional properties

## Tool Contracts

### aws_translate
- **Input:** `{intent: string, region?: string}`
- **Output:** `{command, explanation, detailed_explanation, risk_level, estimated_cost, requires_dry_run, affected_resources, flags_used}`
- **Side effects:** None (read-only translation)
- **Error:** Returns error message as text content

### aws_execute
- **Input:** `{command: string, dry_run?: boolean}`
- **Output:** `{command, exit_code, stdout, stderr, duration_ms, dry_run}`
- **Side effects:** Executes AWS CLI command (potentially destructive)
- **Important:** Description MUST tell the client to confirm with user before calling

### aws_cost_preview
- **Input:** `{command: string}`
- **Output:** `{command, estimated_cost, risk_level, warnings}`
- **Side effects:** None

### aws_explain
- **Input:** `{command: string}`
- **Output:** Markdown explanation text
- **Side effects:** Calls Bedrock for explanation generation

## Implementation Rules

1. All tool handlers are `async` functions
2. Always return `list[TextContent]` — wrap output in JSON string
3. Catch ALL exceptions in `call_tool` and return error as TextContent (never crash the server)
4. Each tool handler instantiates its own dependencies (no shared state between calls)
5. The MCP server must be stateless — no session context between tool calls

## Testing the MCP Server

To test locally without an MCP client:

```bash
# Start the server
echo '{"jsonrpc":"2.0","method":"initialize","params":{"capabilities":{}},"id":1}' | csgpt mcp serve
```

For proper testing, use the MCP Inspector or integrate with Kiro:

```json
// .kiro/settings/mcp.json
{
  "mcpServers": {
    "cloudshellgpt": {
      "command": "csgpt",
      "args": ["mcp", "serve"],
      "env": {
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

## Adding New Tools

When adding a new MCP tool:
1. Add the `Tool(...)` definition in `list_tools()`
2. Add a handler function `async def _tool_<name>(args) -> list[TextContent]`
3. Add the routing in `call_tool()`
4. Update the README MCP section
5. Add an integration test in `tests/integration/test_mcp.py`
