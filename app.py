import os
import json

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI

from events import EVENTS


load_dotenv()

app = Flask(__name__)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json() or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({
            "response": "Please tell me what you're looking for.",
            "event": None
        })

    # Convert the event list into information that OpenAI can search.
    event_data = "\n".join(
        [
            f"""
Event: {event["name"]}
Time: {event["time"]}
Location: {event["location"]}
Room: {event.get("room", "N/A")}
Description: {event.get("description", "")}
"""
            for event in EVENTS
        ]
    )

    try:
        response = client.responses.create(
            model="gpt-5.6-luna",

            instructions=f"""
You are NAVI, an intelligent navigation robot at Hack the North.

Your job is to understand what a person is looking for and find the
most relevant event from the Hack the North schedule.

The user can ask naturally.

Examples:

"I want to learn about AI"

"Where can I learn about OpenAI?"

"I'm looking for something about security"

"Where can I learn about local LLMs?"

"I want to meet companies"

"What can I do tonight?"

"Where is the OpenAI workshop?"

Use ONLY the events provided below.

Never invent an event.

Never invent a room.

Never invent a location.

Never invent a time.

If the user's request matches an event, return the single most
relevant event.

If several events are reasonable matches, choose the one that is
most directly related to the user's request.

If there is no reasonable match, return event as null.

Keep the response concise, friendly, and grounded, like a helpful
person giving directions. A small touch of dry robot personality
is fine, but do not overdo it, and never let it get in the way of
clarity.

EVENT SCHEDULE:
{event_data}

Return ONLY valid JSON in exactly this structure:

{{
    "response": "A short natural-language response",
    "event": {{
        "name": "Event name",
        "time": "Event time",
        "location": "Event location",
        "room": "Event room"
    }}
}}

If there is no matching event:

{{
    "response": "I couldn't find a matching event in the schedule.",
    "event": null
}}
""",

            input=question
        )

        result = json.loads(response.output_text)

        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({
            "response": "I understood your request, but I couldn't format the result correctly.",
            "event": None
        })

    except Exception as error:
        print("OpenAI error:", error)

        return jsonify({
            "response": "I'm having trouble connecting right now. Please try again.",
            "event": None
        })


if __name__ == "__main__":
    app.run(debug=True)
    