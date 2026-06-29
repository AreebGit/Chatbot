import json
import re
import time

from google import genai

from Chatbot_Backend.config import API_KEY

from Chatbot_Backend.db import (
    save_message,
    get_recent_messages,
    get_health_facts,
    save_health_fact
)

import jwt
from datetime import datetime, timedelta

SECRET_KEY = "areeb2985"


def create_token(user_id):

    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=7)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token


def verify_token(token):

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload

    except jwt.ExpiredSignatureError:
        return None

    except jwt.InvalidTokenError:
        return None


def load_system_prompt():

    with open("Chatbot_Backend/system_prompt.json", "r") as file:
        data = json.load(file)

    return data["system_prompt"]


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
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        facts[key] = value

        clean_response = re.sub(
            pattern, '', response_text, flags=re.DOTALL
        ).strip()
    else:
        clean_response = response_text.strip()

    return clean_response, facts


def build_health_facts_section(user_id):

    facts = get_health_facts(user_id)

    if not facts:
        return ""

    facts_text = "\nKNOWN USER HEALTH FACTS:\n"

    for fact_key, fact_value in facts:
        facts_text += f"- {fact_key}: {fact_value}\n"

    return facts_text


def count_tokens(text):
    """
    Rough token estimate — 1 token ≈ 4 characters.
    Gemini's tokeniser isn't exposed in the basic SDK
    so this is a close enough approximation for analytics.
    """
    return len(text) // 4


def ask_llm(user_query, session_id, user_id):

    input_tokens = count_tokens(user_query)

    save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content=user_query,
        input_tokens=input_tokens
    )

    system_prompt = load_system_prompt()
    health_facts_section = build_health_facts_section(user_id)
    chat_history = get_recent_messages(session_id=session_id, limit=20)

    prompt = f"""
SYSTEM:

{system_prompt}

{health_facts_section}

CONVERSATION:
"""

    for role, content in chat_history:
        prompt += f"{role}: {content}\n"

    prompt += "\nassistant:"

    print("\n========== PROMPT ==========")
    print(prompt)
    print("============================\n")

    client = genai.Client(api_key=API_KEY)

    # Start timer just before the Gemini call
    start_time = time.time()

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    # Stop timer immediately after response
    latency_ms = int((time.time() - start_time) * 1000)

    raw_response = response.text
    output_tokens = count_tokens(raw_response)

    clean_response, facts = parse_health_facts(raw_response)

    for fact_key, fact_value in facts.items():
        save_health_fact(
            user_id=user_id,
            fact_key=fact_key,
            fact_value=fact_value
        )
        print(f"HEALTH FACT SAVED: {fact_key} = {fact_value}")

    print(f"LATENCY: {latency_ms}ms | INPUT TOKENS: {input_tokens} | OUTPUT TOKENS: {output_tokens}")

    save_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content=clean_response,
        output_tokens=output_tokens,
        latency_ms=latency_ms
    )

    return clean_response