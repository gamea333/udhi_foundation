"""Part A pipeline: call Gemini, check the SVG, retry once with the reasons."""
import os
import re
import time
from datetime import datetime, timezone

from google import genai
from google.genai import errors, types

from checks import all_passed, run_checks

# Try the primary model first; if it is still overloaded after all backoff
# attempts, fall back to the next one.
PRIMARY = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
MODELS = [PRIMARY] + [m for m in ["gemini-3.5-flash-lite", "gemini-3.5-flash"] if m != PRIMARY]

# The free tier costs $0. These are PAID standard-tier prices (USD per 1M tokens)
# used to estimate production cost, as of Nov 2026. Flash-Lite matches several
# sources; Flash is from third-party write-ups, not confirmed on Google's page.
# https://ai.google.dev/gemini-api/docs/pricing
PRICES = {
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
}

MAX_API_ATTEMPTS = 3          # attempts per model on 429/503
RETRYABLE_CODES = {429, 503, 504}  # 504 = Google-side deadline expired, also transient
REQUEST_TIMEOUT_MS = 180_000  # don't let one call hang forever

# Low thinking: with default thinking gemini-3.5-flash took ~212s per diagram,
# with "low" ~64s, and the SVGs still pass the checks.
GEN_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_level="low"),
)


class GenerationError(Exception):
    """Raised with a human-readable message when the API keeps failing."""


PROMPT = """You are drawing a diagram for a UK GCSE {subject} lesson video.

Concept: {concept}
Teach exactly this: {text}

Return ONE self-contained animated SVG. Rules:
- Root <svg> with xmlns="http://www.w3.org/2000/svg" and viewBox="0 0 600 400". No width/height.
- First child must be a <title> naming the concept.
- At least 3 <text> labels. Label these terms exactly: {terms}.
- Every shape and label must stay fully inside the viewBox (leave a 20px margin).
- Use absolute coordinates; avoid the transform attribute on static shapes.
- Include at least one animation (SMIL <animate>/<animateTransform>, or CSS @keyframes
  inside a <style> element) that helps explain the concept.
- No <script>, no external images or fonts.
- It must be strict, valid XML: write & as &amp; everywhere (even in comments),
  and wrap the contents of any <style> element in <![CDATA[ ... ]]>.
- Plain white background, clear readable font-size (at least 14).

Return ONLY the SVG code, no explanation, no markdown fences."""


def get_client() -> genai.Client:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GenerationError("GEMINI_API_KEY is not set on the server.")
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))


def extract_svg(text: str) -> str:
    """Models often wrap the SVG in ```xml fences or add chatter; pull out just the <svg>."""
    m = re.search(r"<svg[\s\S]*</svg>", text or "")
    return m.group(0) if m else (text or "").strip()


def call_model(client, prompt: str, log: list) -> dict:
    """One model call: backoff on 429/503 up to 3 attempts per model, then try
    the fallback model. Returns svg, model, token counts and api_retries."""
    api_retries = 0
    last_code = None
    for model in MODELS:
        for attempt in range(1, MAX_API_ATTEMPTS + 1):
            try:
                resp = client.models.generate_content(model=model, contents=prompt, config=GEN_CONFIG)
                u = resp.usage_metadata
                return {
                    "svg": extract_svg(resp.text),
                    "model": model,
                    "input_tokens": u.prompt_token_count or 0,
                    # thinking tokens are billed as output, so count them too
                    "output_tokens": (u.candidates_token_count or 0) + (u.thoughts_token_count or 0),
                    "api_retries": api_retries,
                }
            except errors.APIError as e:
                if e.code not in RETRYABLE_CODES:
                    raise GenerationError(f"Gemini API error {e.code} ({model}): {e.message}") from e
                last_code = e.code
                api_retries += 1
                if attempt < MAX_API_ATTEMPTS:
                    wait = 5 * 2 ** (attempt - 1)  # 5s, 10s
                    log.append(f"{model}: API {e.code} on attempt {attempt}, waiting {wait}s")
                    time.sleep(wait)
                else:
                    log.append(f"{model}: API {e.code} {MAX_API_ATTEMPTS} times, giving up on this model")
    reason = {429: "rate limit", 503: "overloaded", 504: "timed out"}.get(last_code, "error")
    raise GenerationError(
        f"Gemini returned {last_code} ({reason}) on every model ({', '.join(MODELS)}). "
        "Free-tier limits are low; try again in a minute."
    )


def generate_one(concept: dict, client=None) -> dict:
    """Run the full Part A flow for one concept and return a result record."""
    client = client or get_client()
    log: list[str] = []
    prompt = PROMPT.format(
        subject=concept["subject"], concept=concept["concept"],
        text=concept["text"], terms=", ".join(concept["key_terms"]),
    )

    calls = [call_model(client, prompt, log)]
    svg = calls[0]["svg"]
    checks = run_checks(svg, concept["key_terms"])
    retries = 0

    if not all_passed(checks):
        # Retry ONCE, telling the model exactly what failed.
        failures = [f"- {name}: {c['reason']}" for name, c in checks.items() if not c["passed"]]
        log.append("Checks failed, retrying:\n" + "\n".join(failures))
        retry_prompt = (
            prompt
            + "\n\nYour previous SVG failed these automated checks:\n"
            + "\n".join(failures)
            + "\n\nHere is your previous SVG:\n" + svg
            + "\n\nFix every problem and return the complete corrected SVG only."
        )
        calls.append(call_model(client, retry_prompt, log))
        svg = calls[-1]["svg"]
        checks = run_checks(svg, concept["key_terms"])
        retries = 1

    # Sum tokens and cost over every call (each priced at the model it used).
    tin = sum(c["input_tokens"] for c in calls)
    tout = sum(c["output_tokens"] for c in calls)
    cost = sum(
        c["input_tokens"] / 1e6 * PRICES[c["model"]]["input"]
        + c["output_tokens"] / 1e6 * PRICES[c["model"]]["output"]
        for c in calls
    )
    return {
        "id": concept["id"],
        "concept": concept["concept"],
        "subject": concept["subject"],
        "model": calls[-1]["model"],  # model that produced the final SVG
        "svg": svg,
        "checks": checks,
        "passed": all_passed(checks),
        "input_tokens": tin,
        "output_tokens": tout,
        "cost_usd": round(cost, 6),
        "retries": retries,           # check-failure retries (max 1)
        "api_retries": sum(c["api_retries"] for c in calls),  # 429/503 backoff retries
        "log": log,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
