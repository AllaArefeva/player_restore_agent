"""Local LLM-as-judge for `custom_response_quality` (see eval_config.yaml)."""

from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel


class _Verdict(BaseModel):
    score: int  # 1-5
    explanation: str


def _extract_text(content_obj: Any) -> str:
    """Extracts text parts from Content dict or string."""
    if isinstance(content_obj, str):
        return content_obj
    if isinstance(content_obj, dict):
        if "parts" in content_obj:
            texts = [p.get("text", "") for p in content_obj["parts"] if "text" in p]
            return " ".join(texts)
        if "response" in content_obj:
            return _extract_text(content_obj["response"])
        if "content" in content_obj:
            return _extract_text(content_obj["content"])
    return str(content_obj or "")


def evaluate(instance):
    reference = instance.get("reference")
    rubric = (
        "Grade the agent's final response on a 1-5 scale (1 poor, 5 excellent) for "
        "accuracy, customer support empathy, relevance, and clarity in the context of 2K MyPlayer restoration."
    )
    if reference:
        rubric += (
            " The response should agree with the expected answer below; penalize "
            "factual disagreement with it."
        )

    prompt_text = _extract_text(instance.get("prompt", ""))
    response_text = _extract_text(instance.get("response", ""))
    ref_text = _extract_text(reference) if reference else ""

    prompt = (
        f"You are an expert QA evaluator for an enterprise 2K Player Support AI assistant. {rubric}\n"
        f"User Prompt / Context: {prompt_text}\n"
        f"Agent Final Response: {response_text}\n"
    )
    if ref_text:
        prompt += f"Expected Behavior / Ground Truth: {ref_text}\n"
    prompt += f"Full Agent Trace: {instance.get('agent_data', '')}\n"

    client = genai.Client()  # AI Studio (GEMINI_API_KEY) or Agent Platform (ADC)
    response = client.models.generate_content(
        model="gemini-3.7-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,  # deterministic grading
            response_mime_type="application/json",
            response_schema=_Verdict,  # guaranteed schema-valid JSON
        ),
    )
    verdict = response.parsed
    if verdict is None:  # model returned nothing usable
        return {"score": 0, "explanation": response.text or ""}
    return {"score": max(1, min(5, verdict.score)), "explanation": verdict.explanation}
