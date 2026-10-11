"""A2A client: discover the code review agent, send it a diff, stream the result."""
import asyncio
import sys

import httpx

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_data_parts, get_text_parts, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState

AGENT_URL = "http://localhost:9999"


async def ask(client, text, task_id=None, context_id=None):
    message = new_text_message(text, role=Role.ROLE_USER, task_id=task_id, context_id=context_id)
    state = None
    async for event in client.send_message(SendMessageRequest(message=message)):
        if event.HasField("task"):
            task_id, context_id = event.task.id, event.task.context_id
        if event.HasField("status_update"):
            status = event.status_update.status
            state = status.state
            print(f"\n[status] {TaskState.Name(state)}")
            if text := "".join(get_text_parts(status.message.parts)):
                print(text)
        if event.HasField("artifact_update"):
            parts = event.artifact_update.artifact.parts
            print("".join(get_text_parts(parts)), end="", flush=True)
            for data in get_data_parts(parts):
                print("\n[findings]")
                for f in data["findings"]:
                    print(f"  {f['severity'].upper():6} {f['file']}: {f['issue']}")
    return task_id, context_id, state


async def main(diff: str) -> None:
    # LLM-backed agents can go quiet for seconds; the default read timeout is too short.
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as http:
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        print(f"Discovered: {card.name} - {[skill.name for skill in card.skills]}")

        client = await create_client(card, ClientConfig(streaming=True, httpx_client=http))
        task_id, context_id, state = await ask(client, diff)
        if state == TaskState.TASK_STATE_INPUT_REQUIRED:
            path = input("\nPath to a diff file: ")
            await ask(client, open(path).read(), task_id, context_id)


if __name__ == "__main__":
    diff = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    asyncio.run(main(diff))
