"""
Real LLM agent with spatial reasoning loop, traced with flow-xray.

Architecture (from plan):
  User query → Planner → [reason / tool / answer] → Verifier → Output
  State graph tracks visited states to avoid loops.

Run:
    python examples/real_agent.py "Почему небо голубое?"

Or via CLI:
    flow-xray run examples/real_agent.py --html agent.html
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

from flow_xray import trace

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# --- State graph (canonical dedup) -------------------------------------------

state_graph: dict[str, dict] = {}


def canonical_key(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()[:12]


@trace
def remember_state(label: str, content: str) -> str:
    key = canonical_key(content)
    if key in state_graph:
        return f"[already visited: {key}]"
    state_graph[key] = {"label": label, "content": content[:300]}
    return key


# --- LLM calls ---------------------------------------------------------------

@trace
def llm_call(prompt: str, *, system: str = "You are a concise reasoning assistant.") -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=300,
        temperature=0.3,
    )
    if resp.usage:
        trace.meta(
            model=resp.model,
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
            total_tokens=resp.usage.total_tokens,
        )
    return resp.choices[0].message.content.strip()


# --- Agent steps --------------------------------------------------------------

@trace
def planner(query: str, context: str) -> dict:
    raw = llm_call(
        f"Given the user question and context, decide the next action.\n"
        f"Question: {query}\n"
        f"Context so far: {context or 'none'}\n\n"
        f"Reply ONLY with JSON: {{\"action\": \"reason\" | \"tool\" | \"answer\", \"detail\": \"...\"}}"
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "answer", "detail": raw}


@trace
def reason_step(query: str, detail: str) -> str:
    thought = llm_call(
        f"Think step by step about: {query}\nFocus on: {detail}\nGive a concise reasoning chain."
    )
    remember_state("reason", thought)
    return thought


@trace
def tool_step(detail: str) -> str:
    result = llm_call(
        f"Simulate a knowledge lookup for: {detail}\n"
        f"Return factual information as if you queried an encyclopedia.",
        system="You are a factual knowledge base. Return only facts.",
    )
    remember_state("tool", result)
    return result


@trace
def verifier(query: str, answer: str) -> dict:
    raw = llm_call(
        f"Verify this answer to the question.\n"
        f"Question: {query}\n"
        f"Answer: {answer}\n\n"
        f"Reply ONLY with JSON: {{\"pass\": true/false, \"feedback\": \"...\"}}"
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"pass": True, "feedback": raw}


@trace
def agent(query: str) -> str:
    context = ""
    for step in range(4):
        plan = planner(query, context)
        action = plan.get("action", "answer")
        detail = plan.get("detail", "")

        if step == 0 and action == "answer":
            action = "tool"
            detail = detail or query

        if action == "reason":
            thought = reason_step(query, detail)
            context += f"\n[reason] {thought}"
        elif action == "tool":
            data = tool_step(detail)
            context += f"\n[tool] {data}"
        else:
            draft = llm_call(f"Answer the question: {query}\nUsing context: {context}\nBe concise.")
            check = verifier(query, draft)
            if check.get("pass"):
                remember_state("final_answer", draft)
                return draft
            context += f"\n[verifier feedback] {check.get('feedback', '')}"

    return llm_call(f"Give your best answer to: {query}\nContext: {context}")


# --- Entry --------------------------------------------------------------------

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "Почему небо голубое?"
    result = trace.run(agent, q)
    result.to_html("agent_trace.html", title=f"Agent: {q[:60]}")
    print(f"\nAnswer: {result.return_value}")
    print(f"States explored: {len(state_graph)}")
    print("Wrote agent_trace.html — open in browser.")
else:
    q = "Почему небо голубое?"
    agent(q)
