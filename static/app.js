async function sendMessage() {

    const input =
        document.getElementById("message-input");

    const message = input.value;

    if (!message) return;

    const chatBox =
        document.getElementById("chat-box");

    chatBox.innerHTML += `
        <div class="mb-2">
            <b>You:</b> ${message}
        </div>
    `;

    input.value = "";

    const response = await fetch(
        "/send-message",
        {
            method: "POST",

            headers: {
                "Content-Type":
                    "application/json"
            },

            body: JSON.stringify({
                user_id: "areeb",
                session_id: "chat_" + Date.now(),
                incoming_message: message
            })
        }
    );

    const data =
        await response.json();

    chatBox.innerHTML += `
        <div class="mb-4">
            <b>Bot:</b> ${data.response}
        </div>
    `;

    chatBox.scrollTop =
        chatBox.scrollHeight;
}
document
    .getElementById("message-input")
    .addEventListener(
        "keypress",
        function(event){

            if(event.key === "Enter"){
                sendMessage();
            }

        }
    );