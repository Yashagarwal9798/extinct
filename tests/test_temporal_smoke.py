"""Talks to the real Temporal dev server (docker compose up -d temporal).
Skipped when it isn't running, so the rest of the suite works without Docker."""

import uuid
from datetime import timedelta

import pytest
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

ADDRESS = "localhost:7233"


@activity.defn
async def greet(name: str) -> str:
    return f"hello {name}"


@workflow.defn
class SmokeWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        # Workflow code only decides; the activity does the work.
        return await workflow.execute_activity(
            greet, name, start_to_close_timeout=timedelta(seconds=10)
        )


@pytest.fixture
async def client():
    try:
        return await Client.connect(ADDRESS)
    except Exception:
        pytest.skip(f"Temporal not running at {ADDRESS} (docker compose up -d temporal)")


async def test_workflow_and_activity_round_trip(client):
    queue = f"smoke-{uuid.uuid4()}"
    async with Worker(client, task_queue=queue, workflows=[SmokeWorkflow], activities=[greet]):
        result = await client.execute_workflow(
            SmokeWorkflow.run, "temporal", id=f"smoke-{uuid.uuid4()}", task_queue=queue
        )
    assert result == "hello temporal"
