from fastapi import FastAPI, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# This lets us read the Authorization header from incoming requests
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from agent import ask_llm

from db import (
    get_all_messages,
    get_messages_by_user,
    get_message_by_id,
    get_analytics,
    upsert_user,
    get_all_users,
    get_user,
    update_feedback,
    get_user_by_phone,
    save_user_fact,
    get_user_facts,
)
from agent import create_token
from agent import verify_token

app = FastAPI()

# Allow the browser to talk to this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(
    directory="templates"
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

# ─────────────────────────────────────────
# AUTH DEPENDENCY
# ─────────────────────────────────────────
#
# Think of this as the bouncer at the door.
# FastAPI will run this function automatically
# before any endpoint that lists it as a dependency.
#
# It reads the "Authorization: Bearer <token>"
# header from the request, verifies the token,
# and returns the user_id inside it.
#
# If the token is missing or invalid, it stops
# the request and returns a 401 error immediately.
#
bearer_scheme = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    # credentials.credentials is the actual token string
    token = credentials.credentials

    payload = verify_token(token)

    if payload is None:
        # Token is expired or tampered with — reject the request
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token. Please log in again."
        )

    # Return the user_id so the endpoint can use it if needed
    return payload["user_id"]


# ─────────────────────────────────────────
# PUBLIC ENDPOINTS (no token needed)
# ─────────────────────────────────────────


@app.get("/chat", include_in_schema=False)
def chat_ui(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

# Login: public because this is HOW you get the token
@app.get("/login/{phone_number}", include_in_schema=False)
def login(phone_number: str):

    user = get_user_by_phone(phone_number)

    if not user:
        return {
            "exists": False,
            "message": "User not found"
        }

    user_id = user[1]
    history = get_messages_by_user(user_id)
    token = create_token(user_id)

    return {
        "exists": True,
        "token": token,
        "user": user,
        "history": history
    }

# This is the endpoint the original Swagger has at the top.
# You call it with a user_id and it gives you back a token.
# In Swagger UI, you then click the 🔒 Authorize button,
# paste the token, and all locked endpoints become usable.
#
# Why is this separate from /login?
# /login is for the website — it looks up a user by phone number.
# /generate-bearer-token is for developers/testing — you directly
# say "give me a token for this user_id" without needing a phone number.
#
@app.post("/generate-bearer-token")
def generate_bearer_token(data: dict):

    user_id = data.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="user_id is required"
        )

    token = create_token(user_id)

    return {
        "access_token": token,
        "token_type": "bearer"
    }

# Register: public because new users don't have a token yet
# After registering, the frontend calls /login to get their token
@app.post("/upsert-user")
def register_user(
    data: dict,
    current_user: str = Depends(get_current_user)
):

    upsert_user(
        user_id=data["user_id"],
        name=data["name"],
        email=data["email"],
        phone_number=data["phone_number"]
    )

    # Also issue a token immediately so the user
    # doesn't need a separate login step
    token = create_token(data["user_id"])

    return {
        "message": "User saved",
        "token": token
    }


# ─────────────────────────────────────────
# PROTECTED ENDPOINTS (token required)
# ─────────────────────────────────────────
#
# Notice the extra parameter:
#   current_user: str = Depends(get_current_user)
#
# This tells FastAPI: "before running this function,
# run get_current_user first. If it raises an error,
# stop here. If it succeeds, pass the user_id in."
#

@app.post("/send-message")
def send_message(
    data: dict,
    current_user: str = Depends(get_current_user)
):
    user_id = data["user_id"]
    session_id = data["session_id"]
    incoming_message = data["incoming_message"]

    print("USER:", user_id)
    print("SESSION:", session_id)
    print("MESSAGE:", incoming_message)

    response = ask_llm(
        user_query=incoming_message,
        session_id=session_id,
        user_id=user_id
    )

    return {"response": response}


@app.post("/update-feedback")
def update_feedback_endpoint(
    data: dict,
    current_user: str = Depends(get_current_user)
):
    session_id = data["session_id"]
    feedback = data["feedback"]

    update_feedback(
        session_id=session_id,
        feedback=feedback
    )

    return {"message": "Feedback updated"}


@app.get("/get-message/{message_id}")
def single_message(
    message_id: int,
    current_user: str = Depends(get_current_user)
):
    return get_message_by_id(message_id)


@app.get("/messages/{user_id}")
def user_messages(
    user_id: str,
    current_user: str = Depends(get_current_user)
):
    return get_messages_by_user(user_id)


@app.get("/messages")
def messages(
    current_user: str = Depends(get_current_user)
):
    return get_all_messages()


@app.get("/users/{user_id}")
def user(
    user_id: str,
    current_user: str = Depends(get_current_user)
):
    return get_user(user_id)


@app.get("/users")
def users(
    current_user: str = Depends(get_current_user)
):
    return get_all_users()


@app.get("/analytics")
def analytics(
    current_user: str = Depends(get_current_user)
):
    return get_analytics()

@app.get("/")
def root():
    return {"message": "Happy Tummy API"}
