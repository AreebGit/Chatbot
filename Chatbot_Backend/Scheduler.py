import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from google import genai

from config import API_KEY
from db import (
    get_last_3_days_user_queries,
    get_health_facts,
    update_persona_traits
)


SCHEDULER_PROMPT = """
You are a health profile analyst for Aashirvaad, a nutrition assistant.

Your job is to analyse a user's recent conversation history and infer new,
distinct health-related traits that are NOT already in their known facts.

KNOWN FACTS (already saved — do NOT repeat these):
{existing_facts}

RECENT CONVERSATIONS:
{conversations}

Guidelines:
- Return ONLY traits that are new and not already captured in the known facts above
- Infer soft signals too — e.g. if someone repeatedly asks about low-calorie meals,
  infer "goal: weight loss" even if they never said it explicitly
- Valid categories: condition, allergy, diet, goal, age, gender
- If you find nothing new, return exactly: NONE
- Do NOT include explanations, bullet points, or any other text

Output format (one per line):
fact_key: fact_value
"""


def count_tokens(text):
    return len(text) // 4


async def run_personality_analysis():
    """
    Runs every 3 days. For each active user:
    1. Fetches their last 3 days of conversations
    2. Fetches their existing health facts (from personality_info)
    3. Asks Gemini to infer only NEW traits not already known
    4. Saves new traits and accumulates token/cost totals into user_persona
    """
    logging.info("Scheduler: starting batch personality analysis")

    try:
        user_data_list = get_last_3_days_user_queries()
        logging.info(f"Scheduler: found {len(user_data_list)} active users")

        client = genai.Client(api_key=API_KEY)

        for user_data in user_data_list:
            user_id = user_data['user_id']
            conversations = user_data['conversations']

            if not conversations:
                continue

            # Fetch existing facts so we can tell the LLM what's already known
            existing_facts = get_health_facts(user_id)

            existing_facts_text = "\n".join(
                f"- {key}: {value}" for key, value in existing_facts
            ) if existing_facts else "None"

            # Only send user messages to the LLM
            conversation_text = "\n".join(
                f"user: {conv['user_question']}"
                for conv in conversations
                if conv.get('user_question')
            )

            if not conversation_text.strip():
                logging.info(f"Scheduler: no conversations for {user_id}, skipping")
                continue

            prompt = SCHEDULER_PROMPT.format(
                existing_facts=existing_facts_text,
                conversations=conversation_text
            )

            logging.info(f"Scheduler: analysing user {user_id}")

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            response_text = response.text.strip() if response.text else ""

            # Token and cost tracking for the scheduler call
            prompt_tokens = count_tokens(prompt)
            completion_tokens = count_tokens(response_text)
            total_tokens = prompt_tokens + completion_tokens
            from Chatbot_Backend.config import USD_INR_CONVERSION_RATE
            cost_usd = (prompt_tokens / 1_000_000 * 0.30) + (completion_tokens / 1_000_000 * 2.50)
            cost_inr = round(cost_usd * USD_INR_CONVERSION_RATE, 6)

            if not response_text or response_text == "NONE":
                logging.info(f"Scheduler: no new traits for user {user_id}")
                # Still accumulate token costs even if no new traits
                update_persona_traits(user_id, [], cost_inr, total_tokens, prompt_tokens, completion_tokens)
                await asyncio.sleep(1)
                continue

            # Parse new traits
            new_traits = []
            for line in response_text.splitlines():
                line = line.strip()
                if ':' not in line:
                    continue
                key, _, value = line.partition(':')
                key, value = key.strip().lower(), value.strip().lower()
                if not key or not value:
                    continue

                # Double-check not already known
                already_known = any(
                    k.lower() == key and v.lower() == value
                    for k, v in existing_facts
                )
                if already_known:
                    logging.info(f"Scheduler: skipping duplicate '{key}: {value}' for {user_id}")
                    continue

                new_traits.append(f"{key}: {value}")

            update_persona_traits(
                user_id=user_id,
                new_traits=new_traits,
                cost_inr=cost_inr,
                total_tokens=total_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            )

            if new_traits:
                logging.info(f"Scheduler: saved {len(new_traits)} new traits for {user_id}: {new_traits}")
            else:
                logging.info(f"Scheduler: no genuinely new traits for {user_id}")

            await asyncio.sleep(1)

        logging.info("Scheduler: batch personality analysis complete")

    except Exception as e:
        logging.error(f"Scheduler: error during batch analysis: {e}")


def setup_scheduler():
    try:
        scheduler = AsyncIOScheduler()

        job = scheduler.add_job(
            run_personality_analysis,
            trigger=CronTrigger(hour=2, minute=0, day="*/3"),
            id="personality_analysis",
            name="Batch personality analysis",
            replace_existing=True
        )

        scheduler.start()
        logging.info(f"Scheduler: started. Next run at {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        logging.error(f"Scheduler: failed to start: {e}")