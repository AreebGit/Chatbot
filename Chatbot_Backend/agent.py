import json
import re
import time
from typing import Generator

from google import genai

from config import API_KEY, USD_INR_CONVERSION_RATE, SECRET_KEY

from db import (
    add_message,
    get_recent_messages,
    get_health_facts,
    save_health_fact,
    upsert_user
)

import jwt
from datetime import datetime, timedelta


def create_token():
    """Generates a JWT with no user_id — matches Project 1 exactly."""
    payload = {
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token):
    """Verifies the JWT. Returns True if valid, False otherwise."""
    try:
        jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return True
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False


def load_system_prompt():
    with open("system_prompt.json", "r") as f:
        return json.load(f)["system_prompt"]


def parse_health_facts(response_text):
    facts = {}
    pattern = r'\[HEALTH_FACTS\](.*?)\[/HEALTH_FACTS\]'
    match = re.search(pattern, response_text, re.DOTALL)

    if match:
        block = match.group(1).strip()
        if block != "NONE":
            for line in block.splitlines():
                line = line.strip()
                if ':' in line:
                    key, _, value = line.partition(':')
                    key, value = key.strip(), value.strip()
                    if key and value:
                        facts[key] = value

        clean_response = re.sub(pattern, '', response_text, flags=re.DOTALL).strip()
    else:
        clean_response = response_text.strip()

    return clean_response, facts


def build_health_facts_section(user_id):
    facts = get_health_facts(user_id)
    if not facts:
        return ""
    lines = "\n".join(f"- {key}: {value}" for key, value in facts)
    return f"\nKNOWN USER HEALTH FACTS:\n{lines}\n"


def count_tokens(text):
    """Rough estimate: 1 token ≈ 4 characters."""
    return len(text) // 4


def stream_llm(user_query, session_id, user_id, name, age, gender, city) -> Generator[str, None, None]:
    """
    Streams the LLM response chunk by chunk.
    Accepts name/age/gender/city to inject into the prompt, matching Project 1.

    Yields:
      - Plain text chunks as they arrive from Gemini
      - A final JSON object with message_id, latency, tokens, and cost
    """
    # Upsert user details on every message, same as Project 1's add_persona
    upsert_user(user_id, name, age, gender, city)

    system_prompt = load_system_prompt()
    health_facts_section = build_health_facts_section(user_id)
    chat_history = get_recent_messages(session_id=session_id, limit=20)

    # Inject user details into prompt, same as Project 1
    prompt_suffix = f"\nHere are the user details: Name: {name}, age: {age}, gender: {gender}, city: {city}"

    prompt = f"SYSTEM:\n\n{system_prompt}{prompt_suffix}\n\n{health_facts_section}\nCONVERSATION:\n"

    for role, content in chat_history:
        prompt += f"{role}: {content}\n"

    prompt += "\nassistant:"

    print("\n========== PROMPT ==========")
    print(prompt)
    print("============================\n")

    client = genai.Client(api_key=API_KEY)
    start_time = time.time()

    raw_response = ""

    for chunk in client.models.generate_content_stream(
        model="gemini-2.5-flash",
        contents=prompt
    ):
        if chunk.text:
            raw_response += chunk.text
            yield chunk.text

    # Latency in seconds (float), matching Project 1's schema
    latency = round(time.time() - start_time, 3)

    input_tokens = count_tokens(prompt)
    output_tokens = count_tokens(raw_response)
    total_tokens = input_tokens + output_tokens

    # Cost calculation using Gemini 2.5 Flash pricing
    cost_usd = (input_tokens / 1_000_000 * 0.30) + (output_tokens / 1_000_000 * 2.50)
    cost_inr = round(cost_usd * USD_INR_CONVERSION_RATE, 6)

    clean_response, facts = parse_health_facts(raw_response)

    for fact_key, fact_value in facts.items():
        save_health_fact(user_id, fact_key, fact_value)
        print(f"HEALTH FACT SAVED: {fact_key} = {fact_value}")

    print(f"LATENCY: {latency}s | TOKENS: {total_tokens} | COST: ₹{cost_inr}")

    message_id = add_message(
        user_id=user_id,
        session_id=session_id,
        question=user_query,
        answer=clean_response,
        latency=latency,
        total_tokens=total_tokens,
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        cost_inr=cost_inr
    )

    # Final metadata chunk — frontend uses message_id for feedback
    # \n\n suffix matches Project 1's SSE format exactly
    yield json.dumps({
        "message_id": message_id,
        "latency": latency,
        "total_tokens": total_tokens,
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "cost_inr": cost_inr
    }) + "\n\n"