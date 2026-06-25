import json
import re

from google import genai

from Chatbot_Backend.config import API_KEY

from Chatbot_Backend.db import (
    save_message,
    get_recent_messages,
    upsert_user,
    get_user_by_phone,
    get_messages_by_user,
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

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm="HS256"
    )

    return token


def verify_token(token):

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"]
        )
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
    """
    The main LLM appends a [HEALTH_FACTS]...[/HEALTH_FACTS] block
    at the end of every response. This function:
    1. Extracts that block
    2. Parses the key: value pairs inside it
    3. Returns the clean response (without the block) + the facts dict

    This way we make ZERO extra API calls — facts come for free
    from the response we were already getting.
    """

    facts = {}

    # Find the block using regex
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

        # Remove the entire block from the visible response
        clean_response = re.sub(pattern, '', response_text, flags=re.DOTALL).strip()
    else:
        clean_response = response_text.strip()

    return clean_response, facts


def build_health_facts_section(user_id):
    """
    Builds a section of the prompt that tells the LLM
    what it already knows about this user's health.
    This is how the LLM gives personalised advice.
    """

    facts = get_health_facts(user_id)

    if not facts:
        return ""

    facts_text = "\nKNOWN USER HEALTH FACTS:\n"

    for fact_key, fact_value in facts:
        facts_text += f"- {fact_key}: {fact_value}\n"

    return facts_text


def ask_llm(user_query, session_id, user_id):

    # Save the user's message to DB
    save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content=user_query
    )

    # Load system prompt (which now includes fact extraction instructions)
    system_prompt = load_system_prompt()

    # Inject known health facts about this user into the prompt
    health_facts_section = build_health_facts_section(user_id)

    # Get recent conversation history for context
    chat_history = get_recent_messages(
        session_id=session_id,
        limit=20
    )

    # Build the full prompt
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

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    raw_response = response.text

    # Parse out the health facts block from the response.
    # This costs nothing — we're just reading what the LLM
    # already returned, no extra API call needed.
    clean_response, facts = parse_health_facts(raw_response)

    # Save any extracted health facts to DB
    for fact_key, fact_value in facts.items():
        save_health_fact(
            user_id=user_id,
            fact_key=fact_key,
            fact_value=fact_value
        )
        print(f"HEALTH FACT SAVED: {fact_key} = {fact_value}")

    # Save the clean response (without the facts block) to DB
    save_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content=clean_response
    )

    return clean_response