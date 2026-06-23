import json

from google import genai

from config import API_KEY

from db import (
    save_message,
    get_recent_messages,
    upsert_user,
    get_user_by_phone,
    get_messages_by_user,
    get_user_facts,
    save_user_fact  
    
)


def load_system_prompt():

    with open(
        "system_prompt.json",
        "r"
    ) as file:

        data = json.load(file)

    return data["system_prompt"]


def extract_fact(user_message):

    client = genai.Client(
        api_key=API_KEY
    )

    extractor_prompt = f"""
You are a memory extraction system.

Extract long-term user facts.

Return ONLY JSON.

Examples:

User:
My favorite animal is a penguin

Output:
{{"fact_key":"favorite_animal","fact_value":"penguin"}}

User:
My favorite color is blue

Output:
{{"fact_key":"favorite_color","fact_value":"blue"}}

User:
My name is Areeb

Output:
{{"fact_key":"name","fact_value":"Areeb"}}

User:
Hello

Output:
{{}}

User:
What is Python?

Output:
{{}}

User:
{user_message}
"""

    try:

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=extractor_prompt
        )

        text = response.text.strip()

        if text.startswith("```json"):
            text = text.replace("```json", "")
            text = text.replace("```", "")
            text = text.strip()

        fact = json.loads(text)

        return fact

    except Exception as e:

        print("FACT EXTRACTION ERROR:", e)

        return {}


def build_facts_section(user_id):

    facts = get_user_facts(user_id)

    if not facts:
        return ""

    facts_text = "\nKNOWN FACTS:\n"

    for fact_key, fact_value in facts:

        facts_text += (
            f"- {fact_key}: {fact_value}\n"
        )

    return facts_text


def ask_llm(
    user_query,
    session_id,
    user_id
):

    save_message(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content=user_query
    )

    fact = extract_fact(user_query)

    if (
        isinstance(fact, dict)
        and "fact_key" in fact
        and "fact_value" in fact
    ):

        save_user_fact(
            user_id=user_id,
            fact_key=fact["fact_key"],
            fact_value=fact["fact_value"]
        )

        print("FACT SAVED:", fact)

    system_prompt = load_system_prompt()

    facts_section = build_facts_section(
        user_id
    )

    chat_history = get_recent_messages(
        session_id=session_id,
        limit=20
    )

    prompt = f"""
SYSTEM:

{system_prompt}

{facts_section}

CONVERSATION:
"""

    for role, content in chat_history:

        prompt += (
            f"{role}: {content}\n"
        )

    prompt += "\nassistant:"

    print("\n========== PROMPT ==========")
    print(prompt)
    print("============================\n")

    client = genai.Client(
        api_key=API_KEY
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    assistant_response = response.text

    save_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content=assistant_response
    )

    return assistant_response