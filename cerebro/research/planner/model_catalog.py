"""Model configuration for Step 0 planner."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlannerModel:
    id: str
    display_name: str
    provider: str
    weight: int
    token_limit_per_session: int
    tokens_used: int = 0
    consecutive_failures: int = 0
    last_used_at: float | None = None


DEFAULT_PLANNER_MODELS: list[PlannerModel] = [
    PlannerModel(
        id="nvidia/llama-3.3-nemotron-super-49b-v1",
        display_name="Nemotron 49B Super (NVIDIA) - Optimized for Strategic Thinking",
        provider="nvidia",
        weight=35,
        token_limit_per_session=140000,
    ),
    PlannerModel(
        id="nvidia/nemotron-3-super-120b-a12b",
        display_name="Nemotron-3 Super 120B (NVIDIA) - Top Tier Reasoning",
        provider="nvidia",
        weight=34,
        token_limit_per_session=140000,
    ),
    PlannerModel(
        id="meta/llama-3.1-70b-instruct",
        display_name="Llama 3.1 70B (NVIDIA)",
        provider="nvidia",
        weight=33,
        token_limit_per_session=120000,
    ),
    PlannerModel(
        id="qwen/qwen3-next-80b-a3b-thinking",
        display_name="Qwen3 Next 80B Thinking (NVIDIA)",
        provider="nvidia",
        weight=20,
        token_limit_per_session=140000,
    ),
    PlannerModel(
        id="deepseek-reasoner",
        display_name="DeepSeek Reasoner (Direct)",
        provider="deepseek",
        weight=24,
        token_limit_per_session=120000,
    ),
    PlannerModel(
        id="deepseek-chat",
        display_name="DeepSeek Chat (Direct)",
        provider="deepseek",
        weight=23,
        token_limit_per_session=120000,
    ),
    PlannerModel(
        id="deepseek/deepseek-r1",
        display_name="DeepSeek R1 (OpenRouter)",
        provider="openrouter",
        weight=20,
        token_limit_per_session=120000,
    ),
    PlannerModel(
        id="qwen/qwq-32b",
        display_name="QwQ-32B (OpenRouter)",
        provider="openrouter",
        weight=19,
        token_limit_per_session=120000,
    ),
    PlannerModel(
        id="qwen-3-235b-a22b-instruct-2507",
        display_name="Qwen 3 235B (Cerebras)",
        provider="cerebras",
        weight=18,
        token_limit_per_session=100000,
    ),
    PlannerModel(
        id="llama3.1-8b",
        display_name="Llama 3.1 8B (Cerebras)",
        provider="cerebras",
        weight=17,
        token_limit_per_session=140000,
    ),
    PlannerModel(
        id="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
        provider="gemini",
        weight=12,
        token_limit_per_session=120000,
    ),
    PlannerModel(
        id="openai/gpt-5",
        display_name="GPT-5",
        provider="github",
        weight=4,
        token_limit_per_session=70000,
    ),
    PlannerModel(
        id="openai/gpt-5-mini",
        display_name="GPT-5 Mini",
        provider="github",
        weight=4,
        token_limit_per_session=90000,
    ),
    PlannerModel(
        id="openai/gpt-4.1",
        display_name="GPT-4.1",
        provider="github",
        weight=4,
        token_limit_per_session=90000,
    ),
    PlannerModel(
        id="openai/gpt-4.1-mini",
        display_name="GPT-4.1 Mini",
        provider="github",
        weight=3,
        token_limit_per_session=110000,
    ),
    PlannerModel(
        id="openai/gpt-4o",
        display_name="GPT-4o",
        provider="github",
        weight=3,
        token_limit_per_session=90000,
    ),
    PlannerModel(
        id="openai/gpt-4o-mini",
        display_name="GPT-4o Mini",
        provider="github",
        weight=3,
        token_limit_per_session=110000,
    ),
    PlannerModel(
        id="meta-llama-3.1-405b-instruct",
        display_name="Llama 3.1 405B",
        provider="github",
        weight=3,
        token_limit_per_session=80000,
    ),
    PlannerModel(
        id="mistral-large-2411",
        display_name="Mistral Large",
        provider="github",
        weight=2,
        token_limit_per_session=80000,
    ),
    PlannerModel(
        id="meta-llama-3.3-70b-instruct",
        display_name="Llama 3.3 70B",
        provider="github",
        weight=2,
        token_limit_per_session=100000,
    ),
    PlannerModel(
        id="meta-llama-3.1-70b-instruct",
        display_name="Llama 3.1 70B",
        provider="github",
        weight=2,
        token_limit_per_session=100000,
    ),
    PlannerModel(
        id="meta-llama-3.1-8b-instruct",
        display_name="Llama 3.1 8B",
        provider="github",
        weight=2,
        token_limit_per_session=140000,
    ),
    PlannerModel(
        id="cohere-command-r-plus-08-2024",
        display_name="Cohere Command R+",
        provider="github",
        weight=2,
        token_limit_per_session=90000,
    ),
    PlannerModel(
        id="phi-4",
        display_name="Phi-4",
        provider="github",
        weight=1,
        token_limit_per_session=120000,
    ),
    PlannerModel(
        id="deepseek-r1-distill-llama-70b",
        display_name="DeepSeek R1 Distill 70B",
        provider="groq",
        weight=1,
        token_limit_per_session=70000,
    ),
]
