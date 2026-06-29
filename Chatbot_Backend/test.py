from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from Chatbot_Backend.agent import ask_llm, create_token, verify_token

from Chatbot_Backend.db import (
    get_all_messages,
    get_messages_by_user,
    get_message_by_id,
    get_analytics,
    upsert_user,
    get_all_users,
    get_user,
    update_feedback,
    get_user_by_phone,
    get_health_facts,
)

app = FastAPI()

bearer_scheme = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token. Please log in again."
        )

    return payload["user_id"]


# ─────────────────────────────────────────
# PUBLIC ENDPOINTS
# ─────────────────────────────────────────


@app.post("/generate-bearer-token")
def generate_bearer_token(data: dict):

    user_id = data.get("user_id")

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    token = create_token(user_id)

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@app.get("/login/{phone_number}", include_in_schema=False)
def login(phone_number: str):

    user = get_user_by_phone(phone_number)

    if not user:
        return {"exists": False, "message": "User not found"}

    user_id = user[1]
    history = get_messages_by_user(user_id)
    token = create_token(user_id)

    return {
        "exists": True,
        "token": token,
        "user": user,
        "history": history
    }


# ─────────────────────────────────────────
# PROTECTED ENDPOINTS 🔒
# ─────────────────────────────────────────

@app.post("/upsert-user")
def register_user(
    data: dict,
    current_user: str = Depends(get_current_user)
):
    upsert_user(
        user_id=data["user_id"],
        name=data["name"],
        email=data["email"],
        phone_number=data["phone_number"],
        city=data.get("city")
    )

    return {"message": "User saved"}


@app.post("/send-message")
def send_message(
    data: dict,
    current_user: str = Depends(get_current_user)
):
    response = ask_llm(
        user_query=data["incoming_message"],
        session_id=data["session_id"],
        user_id=data["user_id"]
    )

    return {"response": response}


@app.post("/update-feedback", summary="Handle Feedback")
def update_feedback_endpoint(
    data: dict,
    current_user: str = Depends(get_current_user)
):
    update_feedback(
        session_id=data["session_id"],
        feedback=data["feedback"]
    )

    return {"message": "Feedback updated"}


@app.get("/get-message/{message_id}", summary="Get Message")
def single_message(
    message_id: int,
    current_user: str = Depends(get_current_user)
):
    return get_message_by_id(message_id)


@app.get("/messages/{user_id}", summary="Get Messages")
def user_messages(
    user_id: str,
    current_user: str = Depends(get_current_user)
):
    return get_messages_by_user(user_id)


@app.get("/messages", summary="Get All Messages")
def messages(
    current_user: str = Depends(get_current_user)
):
    return get_all_messages()


@app.get("/users/{user_id}", summary="Get Personas")
def user(
    user_id: str,
    current_user: str = Depends(get_current_user)
):
    return get_user(user_id)


@app.get("/users", summary="Get All Personas")
def users(
    current_user: str = Depends(get_current_user)
):
    return get_all_users()


@app.get("/analytics", summary="Get Message Analytics")
def analytics(
    current_user: str = Depends(get_current_user)
):
    return get_analytics()


# Returns health facts for a specific user — used by the dashboard
@app.get("/users/{user_id}/facts", summary="Get User Health Facts", include_in_schema=False)
def user_facts(
    user_id: str,
    current_user: str = Depends(get_current_user)
):
    facts = get_health_facts(user_id)
    return [{"key": k, "value": v} for k, v in facts]

@app.get("/")
def root():
    return {"message": "Happy Tummy API"}