from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles

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
    save_user_fact,
    get_user_facts
)


app = FastAPI()

templates = Jinja2Templates(
    directory="templates"
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

@app.post("/upsert-user")
def register_user(data: dict):

    upsert_user(
        user_id=data["user_id"],
        name=data["name"],
        email=data["email"]
    )

    return {
        "message": "User saved"
    }


@app.post("/send-message")
def send_message(data: dict):

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

    return {
        "response": response
    }

@app.post("/update-feedback")
def update_feedback_endpoint(data: dict):

    session_id = data["session_id"]

    feedback = data["feedback"]

    update_feedback(
        session_id=session_id,
        feedback=feedback
    )

    return {
        "message": "Feedback updated"
    }

@app.get("/get-message/{message_id}")
def single_message(message_id: int):

    return get_message_by_id(message_id)

@app.get("/messages/{user_id}")
def user_messages(user_id: str):

    return get_messages_by_user(user_id)

@app.get("/messages")
def messages():

    return get_all_messages()

@app.get("/users/{user_id}")
def user(user_id: str):

    return get_user(user_id)

@app.get("/users")
def users():

    return get_all_users()

@app.get("/chat")
def chat_ui(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )


@app.get("/analytics")
def analytics():

    return get_analytics()