"""Simple tool executor for LLM function calling."""


async def execute_tool_calls(tool_calls):
    """Execute tool calls and return results."""
    if not tool_calls:
        return []
    
    results = []
    for call in tool_calls:
        tool_call_id = call.get("id", "")
        results.append({
            "role": "tool",
            "content": "Tool execution result",
            "tool_call_id": tool_call_id,
        })
    
    return results