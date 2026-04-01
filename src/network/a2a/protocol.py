"""A2A protocol adapter.

Translates between Intuno's internal message format and the A2A
JSON-RPC wire format.

A2A spec: https://google.github.io/A2A/specification/
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional


# A2A task states
A2A_STATE_SUBMITTED = "submitted"
A2A_STATE_WORKING = "working"
A2A_STATE_INPUT_REQUIRED = "input-required"
A2A_STATE_COMPLETED = "completed"
A2A_STATE_FAILED = "failed"
A2A_STATE_CANCELED = "canceled"

# Mapping from Intuno message status to A2A task state
_STATUS_MAP = {
    "pending": A2A_STATE_SUBMITTED,
    "delivered": A2A_STATE_WORKING,
    "read": A2A_STATE_COMPLETED,
    "failed": A2A_STATE_FAILED,
}

# Mapping from Intuno channel type to A2A concepts
_CHANNEL_MAP = {
    "call": "task",       # synchronous call maps to A2A task
    "message": "message", # async message maps to A2A message
    "mailbox": "message", # mailbox also maps to A2A message (deferred)
}


def intuno_message_to_a2a_task(
    message: dict[str, Any],
    sender_name: str = "",
    recipient_name: str = "",
) -> dict[str, Any]:
    """Convert an Intuno NetworkMessage (as dict) to an A2A Task object."""
    task_id = message.get("id") or str(uuid.uuid4())
    status = message.get("status", "pending")
    content = message.get("content", "")
    metadata = message.get("metadata_") or message.get("metadata") or {}

    a2a_task = {
        "id": str(task_id),
        "status": {
            "state": _STATUS_MAP.get(status, A2A_STATE_SUBMITTED),
            "timestamp": (
                message.get("created_at", datetime.now(timezone.utc)).isoformat()
                if isinstance(message.get("created_at"), datetime)
                else datetime.now(timezone.utc).isoformat()
            ),
        },
        "history": [
            {
                "role": "user",
                "parts": [{"type": "text", "text": content}],
            }
        ],
        "metadata": {
            "intuno_network_id": str(message.get("network_id", "")),
            "intuno_channel": message.get("channel_type", "message"),
            "sender": sender_name,
            "recipient": recipient_name,
            **metadata,
        },
    }

    return a2a_task


def a2a_task_to_intuno_message(
    a2a_task: dict[str, Any],
) -> dict[str, Any]:
    """Convert an A2A Task object to Intuno message format."""
    # Extract content from history
    content = ""
    history = a2a_task.get("history", [])
    if history:
        last_entry = history[-1]
        parts = last_entry.get("parts", [])
        text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
        content = "\n".join(text_parts)

    # Map A2A state back to Intuno status
    state = a2a_task.get("status", {}).get("state", A2A_STATE_SUBMITTED)
    reverse_status_map = {
        A2A_STATE_SUBMITTED: "pending",
        A2A_STATE_WORKING: "delivered",
        A2A_STATE_COMPLETED: "read",
        A2A_STATE_FAILED: "failed",
        A2A_STATE_INPUT_REQUIRED: "pending",
        A2A_STATE_CANCELED: "failed",
    }

    a2a_metadata = a2a_task.get("metadata", {})

    return {
        "content": content,
        "channel_type": a2a_metadata.get("intuno_channel", "message"),
        "status": reverse_status_map.get(state, "pending"),
        "metadata": {
            "a2a_task_id": a2a_task.get("id"),
            "a2a_state": state,
            **{
                k: v
                for k, v in a2a_metadata.items()
                if not k.startswith("intuno_")
            },
        },
    }


def build_a2a_json_rpc_response(
    result: Any,
    request_id: Optional[str | int] = None,
) -> dict[str, Any]:
    """Wrap a result in a JSON-RPC 2.0 response envelope."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def build_a2a_json_rpc_error(
    code: int,
    message: str,
    request_id: Optional[str | int] = None,
    data: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error,
    }
