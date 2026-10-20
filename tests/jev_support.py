"""Purpose: serve synthetic Jev answers to tests through the real TypeSafe SDK, its HTTP replaced by
an httpx2 MockTransport, so tests exercise the client's mechanics without a key or a hosted call.
Answers from here are fixtures for mechanics; claims about what Jev answers rest on captured
replays."""

from __future__ import annotations

import json

import httpx2
from typesafe_sdk import RetryPolicy, TypeSafeClient
from reading_support import INCIDENT


MODEL = INCIDENT.model


# am[verifies a-jev-client-1016]
def client(handler):
    """A factory for the real SDK client with its HTTP replaced by handler, no retries, no
    compression."""

    return lambda: TypeSafeClient(
        api_key="synthetic-test-key",
        transport=httpx2.MockTransport(handler),
        retry=RetryPolicy(max_retries=0),
        compression=False,
    )


# am[verifies a-jev-client-1016]
def answering(answer_for, *, model=MODEL, calls=None):
    """A handler answering every asked question with answer_for(question_id, state), recording each
    request body in calls when given."""

    def handler(request):
        body = json.loads(request.content)
        if calls is not None:
            calls.append(body)
        return httpx2.Response(
            200,
            json={
                "model": model,
                "answers": {
                    q: {"type": "choice", "choice": max(p, key=p.get), "confidence": max(p.values()),
                        "probabilities": p}
                    for q in body["questions"]
                    for p in [answer_for(q, body["state"])]
                },
                "usage": {"input_tokens": 100, "output_tokens": 3},
            },
        )

    return handler


# Every proposition supported at 0.9 and the mood declarative: one sure answer per question.
# am[verifies a-jev-client-1016]
def sure(q, state):
    del state
    return {"supported": 0.9, "contradicted": 0.05, "unknown": 0.05} if q != "mood" else {
        "query": 0.05, "directive": 0.05, "declarative": 0.9}
