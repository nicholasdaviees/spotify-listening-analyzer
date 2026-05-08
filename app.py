import json
import re

import ollama
from flask import Flask, request, render_template
from datetime import datetime

from analysis import (
    calculateListeningStats,
    compute_artist_percentage,
    has_filter,
    run_analysis_query,
)
from prompts import (
    get_artist_percentage_intent_prompt,
    get_explanation_prompt,
    get_planner_prompt,
)

RAW_LISTENING_HISTORY = [] # Stores all uploaded listening history entries
DASHBOARD_RESULT = {} # Stores listening stats from results.html
CHAT_HISTORY = []

app = Flask(__name__)

def return_with_memory(answer, original_question):
    CHAT_HISTORY.append({"role": "user", "content": original_question})
    CHAT_HISTORY.append({"role": "assistant", "content": answer})
    CHAT_HISTORY[:] = CHAT_HISTORY[-10:]
    return {"answer": answer}

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

    RAW_LISTENING_HISTORY = all_entries
    result = calculateListeningStats(all_entries, start_date=start_date, end_date=end_date)
    DASHBOARD_RESULT = result
    return render_template("results.html", result=result)

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
    
    # ******************TODO: make this more dynamic? Returns false data******************
    # BEGIN REJECTION OF UNSUPPORTED QUESTIONS
    if any(term in question for term in ["genre", "rap", "hip hop", "pop", "rock"]):
        return return_with_memory(
            "I don't have genre information in your listening history.",
            original_question
        )
    
    if "least" in question:
        return return_with_memory(
            "I don't currently support finding least-listened artists.",
            original_question
        )
    # END REJECTION OF UNSUPPORTED QUESTIONS
    # ******************TODO: make this more dynamic? Returns false data******************
    
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
        return return_with_memory(
            "I could not understand that question as an analysis plan. Try rephrasing it.",
            original_question
        )
    # TODO: fix to include more than one question in multi_aggregation
    if plan.get("type") == "multi_aggregation":
        queries = plan.get("queries", [])

        analysis_result = {}

        if len(queries) > 0:
            analysis_result["query_1"] = run_analysis_query(DASHBOARD_RESULT, RAW_LISTENING_HISTORY, queries[0])

        if len(queries) > 1:
            analysis_result["query_2"] = run_analysis_query(DASHBOARD_RESULT, RAW_LISTENING_HISTORY, queries[1])

    # For single query
    else:
        analysis_result = run_analysis_query(DASHBOARD_RESULT, RAW_LISTENING_HISTORY, plan)

    explanation_prompt = get_explanation_prompt(question, analysis_result)

    explanation_response = ollama.chat(
        model="qwen2.5:14b",
        messages=[{"role": "user", "content": explanation_prompt}]
    )

    answer = explanation_response["message"]["content"]
    return return_with_memory(answer, original_question)

if __name__ == "__main__":
    app.run(debug=True)