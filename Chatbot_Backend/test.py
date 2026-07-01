import logging

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from agent import stream_llm, create_token, verify_token
from config import TOKEN_API_KEY
from models import TokenRequest, UpsertUserRequest, UserMessage, FeedbackUpdate
from Scheduler import setup_scheduler

from db import (
    get_all_messages,
    get_messages_by_user,
    get_message_by_id,
    get_analytics,
    upsert_user,
    get_all_users,
    get_user,
    update_feedback,
    get_health_facts,
)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="HappyTummy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer()


@app.on_event("startup")
async def startup_event():
    setup_scheduler()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    token = credentials.credentials
    is_valid = verify_token(token)

    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token. Please log in again."
        )

    return True


# ─────────────────────────────────────────
# PUBLIC ENDPOINTS
# ─────────────────────────────────────────


@app.post("/generate-bearer-token")
def generate_bearer_token(data: TokenRequest):
    try:
        if not TOKEN_API_KEY:
            raise HTTPException(status_code=500, detail="Server misconfiguration: TOKEN_API_KEY is not set")

        if data.api_key != TOKEN_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

        token = create_token()

        return {
            "success": True,
            "message": "Bearer token generated successfully.",
            "data": {"bearer_token": token},
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "generate_token_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


# ─────────────────────────────────────────
# PROTECTED ENDPOINTS 🔒
# ─────────────────────────────────────────


@app.post("/upsert-user")
def register_user(
    data: UpsertUserRequest,
    current_user: bool = Depends(get_current_user)
):
    try:
        upsert_user(
            user_id=data.user_id,
            name=data.name,
            age=data.age,
            gender=data.gender,
            city=data.city
        )

        return {
            "success": True,
            "message": "User registered successfully.",
            "data": None,
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "upsert_user_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.post("/send-message")
def send_message(
    data: UserMessage,
    current_user: bool = Depends(get_current_user)
):
    """
    Streams the LLM response token by token.
    The last chunk is a JSON object with message_id, latency, and token counts.
    """
    try:
        def response_stream():
            for chunk in stream_llm(
                user_query=data.incoming_message,
                session_id=data.session_id,
                user_id=data.user_id,
                name=data.name,
                age=data.age,
                gender=data.gender,
                city=data.city
            ):
                yield chunk

        return StreamingResponse(
            response_stream(),
            media_type="text/event-stream"
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "send_message_error", "error": str(e), "user_id": data.user_id})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.post("/update-feedback")
def update_feedback_endpoint(
    data: FeedbackUpdate,
    current_user: bool = Depends(get_current_user)
):
    try:
        updated = update_feedback(
            message_id=data.message_id,
            user_feedback=data.user_feedback
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Message not found.")

        logging.info({"event": "feedback_updated", "message_id": data.message_id})

        return {
            "success": True,
            "message": "Feedback updated successfully.",
            "data": None,
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "update_feedback_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.get("/get-message/{message_id}")
def single_message(
    message_id: str,
    current_user: bool = Depends(get_current_user)
):
    try:
        message = get_message_by_id(message_id)

        if not message:
            raise HTTPException(status_code=404, detail="Message not found.")

        return {
            "success": True,
            "message": "Message retrieved successfully.",
            "data": message,
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "get_message_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.get("/messages/{user_id}")
def user_messages(
    user_id: str,
    current_user: bool = Depends(get_current_user)
):
    try:
        messages = get_messages_by_user(user_id)

        if not messages:
            raise HTTPException(status_code=404, detail="No messages found for the user.")

        return {
            "success": True,
            "message": "Messages retrieved successfully.",
            "data": messages,
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "get_messages_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.get("/messages")
def all_messages(
    current_user: bool = Depends(get_current_user)
):
    try:
        messages = get_all_messages()

        if not messages:
            raise HTTPException(status_code=404, detail="No messages found.")

        return {
            "success": True,
            "message": "All messages retrieved successfully.",
            "data": messages,
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "get_all_messages_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.get("/users/{user_id}")
def single_user(
    user_id: str,
    current_user: bool = Depends(get_current_user)
):
    try:
        user = get_user(user_id)

        if not user:
            raise HTTPException(status_code=404, detail=f"No user found for {user_id}.")

        return {
            "success": True,
            "message": "User retrieved successfully.",
            "data": user,
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "get_user_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.get("/users")
def all_users(
    current_user: bool = Depends(get_current_user)
):
    try:
        users = get_all_users()

        if not users:
            raise HTTPException(status_code=404, detail="No users found.")

        return {
            "success": True,
            "message": "All users retrieved successfully.",
            "data": users,
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "get_all_users_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.get("/analytics")
def analytics(
    current_user: bool = Depends(get_current_user)
):
    try:
        data = get_analytics()

        return {
            "success": True,
            "message": "Analytics retrieved successfully.",
            "data": data,
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "get_analytics_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.get("/users/{user_id}/facts", include_in_schema=False)
def user_facts(
    user_id: str,
    current_user: bool = Depends(get_current_user)
):
    try:
        facts = get_health_facts(user_id)
        return {
            "success": True,
            "message": "Health facts retrieved successfully.",
            "data": [{"key": k, "value": v} for k, v in facts],
            "error": None
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error({"event": "get_user_facts_error", "error": str(e)})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.get("/")
def root():
    return {"message": "Hello from root!"}