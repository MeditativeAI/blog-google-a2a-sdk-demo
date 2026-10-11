"""A2A server agent: reviews a git diff with an OpenAI model."""
import os
from collections.abc import AsyncIterator
from typing import Literal

import uvicorn
from openai import AsyncOpenAI
from pydantic import BaseModel
from starlette.applications import Starlette

from a2a.helpers import new_data_part, new_task_from_user_message, new_text_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, TaskState

PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:9999/")
MODEL = os.getenv("OPENAI_MODEL_NAME", "gpt-5.4")
llm = AsyncOpenAI()


class CodeReviewExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        diff = context.get_user_input()
        if "@@" not in diff:
            await updater.requires_input(
                new_text_message("Please send a unified git diff (the output of `git diff`).")
            )
            return

        try:
            review = ""
            async for line in review_lines(diff):
                await updater.add_artifact(
                    [new_text_part(line)], artifact_id="review", name="review", append=bool(review)
                )
                review += line
            await updater.add_artifact(
                [new_text_part("")], artifact_id="review", append=True, last_chunk=True
            )

            # Not streamed, so announce it; a silent connection can hit client timeouts.
            await updater.update_status(
                TaskState.TASK_STATE_WORKING, new_text_message("Extracting findings...")
            )
            findings = await extract_findings(review)
            await updater.add_artifact([new_data_part(findings.model_dump())], name="findings")
        except Exception as exc:
            await updater.failed(new_text_message(f"Review failed: {exc}"))
            return
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


class Finding(BaseModel):
    file: str
    severity: Literal["low", "medium", "high"]
    issue: str
    suggestion: str


class Findings(BaseModel):
    findings: list[Finding]


async def review_lines(diff: str) -> AsyncIterator[str]:
    stream = await llm.chat.completions.create(
        model=MODEL,
        stream=True,
        messages=[
            {"role": "system", "content": "You are a senior engineer reviewing a git diff. "
             "Write a concise markdown review: a short summary, then bullets for bugs, risks "
             "and improvements, naming files. Do not invent problems."},
            {"role": "user", "content": diff},
        ],
    )
    line = ""
    async for chunk in stream:
        if chunk.choices and (token := chunk.choices[0].delta.content):
            line += token
            if "\n" in line:
                yield line
                line = ""
    if line:
        yield line


async def extract_findings(review: str) -> Findings:
    response = await llm.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Extract the concrete issues from this code review."},
            {"role": "user", "content": review},
        ],
        response_format=Findings,
    )
    return response.choices[0].message.parsed


card = AgentCard(
    name="Code Review Agent",
    description="Reviews a git diff: streams a written review and returns structured findings.",
    version="1.0.0",
    supported_interfaces=[
        AgentInterface(url=PUBLIC_URL, protocol_binding="JSONRPC", protocol_version="1.0")
    ],
    capabilities=AgentCapabilities(streaming=True),
    default_input_modes=["text/plain"],
    default_output_modes=["text/markdown", "application/json"],
    skills=[
        AgentSkill(
            id="review_diff",
            name="Code review",
            description="Review a unified git diff for bugs, risks and improvements.",
            tags=["code", "review", "git"],
        )
    ],
)

handler = DefaultRequestHandler(
    agent_executor=CodeReviewExecutor(), task_store=InMemoryTaskStore(), agent_card=card
)
app = Starlette(
    routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, rpc_url="/")
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9999)
