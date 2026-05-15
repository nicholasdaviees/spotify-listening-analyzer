import json
import re
import spotipy

import ollama
from flask import Flask, request, render_template
from datetime import datetime
from spotipy.oauth2 import SpotifyClientCredentials

from dotenv import load_dotenv
load_dotenv()

from services.analysis import (
    calculateListeningStats,
    compute_artist_percentage,
    has_filter,
    run_analysis_query,
)

from services.prompts import (
    get_artist_percentage_intent_prompt,
    get_clarification_prompt,
    get_explanation_prompt,
    get_clarity_prompt,
    get_planner_prompt,
)

RAW_LISTENING_HISTORY = [] # Stores all uploaded listening history entries
DASHBOARD_RESULT = {} # Stores listening stats from results.html
CHAT_HISTORY = []
spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials())

app = Flask(__name__)

def return_with_memory(answer, original_question):
    CHAT_HISTORY.append({"role": "user", "content": original_question})
    CHAT_HISTORY.append({"role": "assistant", "content": answer})
    CHAT_HISTORY[:] = CHAT_HISTORY[-10:]
    return {"answer": answer}

# Begin helper functions to pull artist and song images from Spotify
def get_spotify_artist_image(artist_name):
    if not artist_name:
        return None

    results = spotify.search(q=f"artist:{artist_name}", type="artist", limit=1)
    items = results.get("artists", {}).get("items", [])

    if not items:
        return None

    images = items[0].get("images", [])
    return images[0]["url"] if images else None


def get_spotify_track_image(song_key):
    if not song_key:
        return None

    # Because current songs look like "artist - track"
    if " - " in song_key:
        artist, track = song_key.split(" - ", 1)
        query = f'track:"{track}" artist:"{artist}"'
    else:
        query = song_key

    results = spotify.search(q=query, type="track", limit=1)
    items = results.get("tracks", {}).get("items", [])

    if not items:
        return None

    album_images = items[0].get("album", {}).get("images", [])
    return album_images[0]["url"] if album_images else None
# Begin helper functions to pull artist and song images from Spotify

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_files():
    global RAW_LISTENING_HISTORY, DASHBOARD_RESULT
    files = request.files.getlist("jsonFiles")
    start_date = request.form.get("startDate") or None
    end_date = request.form.get("endDate") or None
    all_entries = []

    for file in files:
        try:
            data = json.load(file)
            if isinstance(data, list):
                all_entries.extend(data)
            else:
                print(f"{file.filename} is not a list")

        except Exception as e:
            print(f"Error reading {file.filename}: {e}")

    # Error checking to make sure date filters are correct
    if start_date is not None or end_date is not None:

        start_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

        dates = [
            datetime.strptime(entry["endTime"], "%Y-%m-%d %H:%M").date()
            for entry in all_entries
            if entry.get("endTime")
        ]

        actual_start_date = min(dates)
        actual_end_date = max(dates)

        if start_date and start_date < actual_start_date:
            return render_template("index.html", error="ERROR: Start date is before your listening history.")

        if end_date and end_date > actual_end_date:
            return render_template("index.html", error="ERROR: End date is after your listening history.")
        
        # Change dates back into strings for calculateListeningStats()
        start_date = start_date.strftime("%Y-%m-%d") if start_date else None
        end_date = end_date.strftime("%Y-%m-%d") if end_date else None

    RAW_LISTENING_HISTORY = all_entries
    result = calculateListeningStats(all_entries, start_date=start_date, end_date=end_date)

    # Grab images for top artist and top song
    result["topArtist"]["image_url"] = get_spotify_artist_image(result["topArtist"]["name"])
    result["topSongMin"]["image_url"] = get_spotify_track_image(result["topSongMin"]["name"])

    DASHBOARD_RESULT = result
    return render_template("results.html", result=result)

@app.route("/results")
def results_page():
    if not DASHBOARD_RESULT:
        return render_template("index.html")
    return render_template("results.html", result=DASHBOARD_RESULT)

@app.route("/llm")
def llm_page():
    return render_template("llm.html")

@app.route("/ask-llm", methods=["POST"])
def ask_llm():
    global CHAT_HISTORY
    data = request.get_json()
    question = data["question"]
    original_question = question

    conversation_context = "\n".join(
        f"{msg['role']}: {msg['content']}"
        for msg in CHAT_HISTORY
    )

    if not RAW_LISTENING_HISTORY:
        return return_with_memory(
            "Please upload your Spotify listening history first.",
            original_question
        )
    
    clarity_prompt = get_clarity_prompt(original_question)

    clarity_response = ollama.chat(
        model="qwen2.5:3b",
        messages=[{"role": "user", "content": clarity_prompt}],
        options={"temperature": 0}
    )

    decision = clarity_response["message"]["content"].strip().lower()

    if "no" in decision:
        clarification_prompt = get_clarification_prompt(original_question)

        clarification_response = ollama.chat(
            model="qwen2.5:14b",
            messages=[{"role": "user", "content": clarification_prompt}]
        )

        answer = clarification_response["message"]["content"]
        return return_with_memory(answer, original_question)
    
    question = question.lower()

    # BEGIN DEAL WITH PERCETAGE QUESTIONS
    intent_prompt = get_artist_percentage_intent_prompt(
        original_question,
        conversation_context
    )

    intent_response = ollama.chat(
        model="qwen2.5:14b",
        messages=[{"role": "user", "content": intent_prompt}],
        options={"temperature": 0}
    )

    # Clean up response
    raw_intent = intent_response["message"]["content"].strip()
    raw_intent = raw_intent.replace("```json", "").replace("```", "").strip()

    # Ensure correct JSON parsing
    try:
        intent_plan = json.loads(raw_intent)
    except Exception:
        intent_plan = {"intent": "other"}

    if intent_plan.get("intent") == "artist_percentage":
        artists = intent_plan.get("artists", []) # Will pull any number of artist mentioned

        if not artists:
            return return_with_memory(
                "Which artist do you want the percentage for?",
                original_question
            )

        results = []
        total_percent = 0
        total_minutes = 0

        # BEGIN FOR LOOP
        # Compute percentage for each artist in list
        for artist in artists:
            data = compute_artist_percentage(DASHBOARD_RESULT, artist)
            # compute_artist_percentage() returns something like: 
            # {
            #    "artist": matched_artist,
            #    "minutes": artist_minutes,
            #    "total": total_minutes,
            #    "percent": artist_percentage
            # }

            if "error" in data:
                return return_with_memory(
                    data["error"],
                    original_question
                )

            results.append(data)
            total_percent += data["percent"]
            total_minutes += data["minutes"]
        # END FOR LOOP

        # For only single artist request
        if len(results) == 1:
            singleArtist = results[0]
            return return_with_memory(
                f"{singleArtist['artist']} accounts for {singleArtist['percent']}% of your total listening time.",
                original_question
            )

        # For multiple artist request
        multipleArtists = ", ".join(data["artist"] for data in results)

        return return_with_memory(
            f"{multipleArtists} together account for {round(total_percent, 2)}% of your total listening time, with {round(total_minutes, 2)} minutes combined.",
            original_question
        )
    # END DEAL WITH PERCENTAGE QUESTIONS
    
    # Convert user question into structured JSON for run_analysis_query()
    planner_prompt = get_planner_prompt(
        original_question,
        conversation_context
    )

    # Call LLM to get analysis plan
    planner_response = ollama.chat(
        model="qwen2.5:14b",
        messages=[{"role": "user", "content": planner_prompt}]
    )

    # Clean up response
    raw_plan = planner_response["message"]["content"].strip()
    raw_plan = raw_plan.replace("```json", "").replace("```", "").strip()

    # Ensure correct JSON parsing
    try:
        plan = json.loads(raw_plan)

        if plan.get("unsupported"):
            return return_with_memory(
                f"I can't answer that because {plan.get('reason', 'that information is not available in your listening history')}.",
                original_question
            )

        question = question.lower()

        # Perform minor correections
        if (
            ("how many minutes" in question or "total" in question)
            and ("between" in question or "-" in question or "from" in question)
            and plan.get("type") != "multi_aggregation"
        ):
            plan["group_by"] = "artist"
            plan["limit"] = 1

        if "specific day" in question or "exact day" in question or "which date" in question:
            plan["group_by"] = "date"
            plan["limit"] = 1

        date_range_match = re.search(
            r"(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}/\d{1,2}/\d{4})",
            question
        )

        if date_range_match and plan.get("type") != "multi_aggregation":
            start_raw = date_range_match.group(1)
            end_raw = date_range_match.group(2)

            # Better format start and end dates into YYYY-MM-DD
            start_date = datetime.strptime(start_raw, "%m/%d/%Y").strftime("%Y-%m-%d")
            end_date = datetime.strptime(end_raw, "%m/%d/%Y").strftime("%Y-%m-%d")

            plan.setdefault("filters", {})
            plan["filters"]["date"] = None
            plan["filters"]["start_date"] = start_date
            plan["filters"]["end_date"] = end_date
            filters = plan.get("filters", {})

            if has_filter(filters, "start_date") and has_filter(filters, "end_date"):
                start_date = filters["start_date"]
                end_date = filters["end_date"]

                # Swap dates if reversed
                if start_date > end_date:
                    filters["start_date"], filters["end_date"] = end_date, start_date

    except Exception:
        # Allow LLM to suggest a better question for user
        clarification_prompt = get_clarification_prompt(original_question)

        clarification_response = ollama.chat(
            model="qwen2.5:14b",
            messages=[{"role": "user", "content": clarification_prompt}]
        )

        answer = clarification_response["message"]["content"]
        return return_with_memory(answer, original_question)
    
    # For multiple queries
    if plan.get("type") == "multi_aggregation":
        queries = plan.get("queries", [])

        analysis_result = {}

        for index, query in enumerate(queries, start=1):
            analysis_result[f"query_{index}"] = run_analysis_query(RAW_LISTENING_HISTORY, query)

    # For single query
    else:
        analysis_result = run_analysis_query(RAW_LISTENING_HISTORY, plan)

    explanation_prompt = get_explanation_prompt(question, analysis_result)

    explanation_response = ollama.chat(
        model="qwen2.5:14b",
        messages=[{"role": "user", "content": explanation_prompt}]
    )

    answer = explanation_response["message"]["content"]
    return return_with_memory(answer, original_question)

if __name__ == "__main__":
    app.run(debug=True)