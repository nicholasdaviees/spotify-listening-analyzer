import json, ollama, re
from flask import Flask, request, render_template
from datetime import datetime
from analysis import (
    calculateListeningStats,
    compute_artist_percentage,
    run_analysis_query,
    has_filter
)

RAW_LISTENING_HISTORY = [] # Stores all uploaded listening history entries
DASHBOARD_RESULT = {} # Stores listening stats from results.html

app = Flask(__name__)

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
    data = request.get_json()
    question = data["question"]

    if not RAW_LISTENING_HISTORY:
        return {"answer": "Please upload your Spotify listening history first."}
    
    # BEGIN DETERMINE IF QUESTION IS MEANINGFUL
    classification_prompt = f"""
    Is the following question a meaningful question about Spotify listening history?

    Answer ONLY "yes" or "no".

    Question:
    {question}
    """

    classification = ollama.chat(
        model="qwen2.5:14b",
        messages=[{"role": "user", "content": classification_prompt}]
    )

    decision = classification["message"]["content"].strip().lower()

    if "no" in decision:
        return {
            "answer": "I couldn't understand that question. Please ask something about your listening history."
        }
    # END DETERMINE IF QUESTION IS MEANINGFUL
    
    question = question.lower()

    # BEGIN DEAL WITH PERCETAGE QUESTIONS
    intent_prompt = f"""
    Classify this Spotify listening-history question.

    Return ONLY valid JSON.

    Possible intents:
    - artist_percentage
    - other

    If the user asks what percent, percentage, share, portion, or fraction of listening comes from one or more artists, use artist_percentage.

    For artist_percentage, extract artist names into an artists list.

    Question:
    {question}

    Examples:

    Question: What percentage of my listening is from Ed Sheeran?
    {{"intent": "artist_percentage", "artists": ["Ed Sheeran"]}}

    Question: How much of my listening comes from Ed Sheeran and Taylor Swift?
    {{"intent": "artist_percentage", "artists": ["Ed Sheeran", "Taylor Swift"]}}

    Question: What are my top songs?
    {{"intent": "other"}}
    """

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
            return {"answer": "Which artist do you want the percentage for?"}

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
                return {"answer": data["error"]}

            results.append(data)
            total_percent += data["percent"]
            total_minutes += data["minutes"]
        # END FOR LOOP

        # For only single artist request
        if len(results) == 1:
            singleArtist = results[0]
            return {
                "answer": f"{singleArtist['artist']} accounts for {singleArtist['percent']}% of your total listening time."
            }

        # For multiple artist request
        multipleArtists = ", ".join(data["artist"] for data in results)

        return {
            "answer": f"{multipleArtists} together account for {round(total_percent, 2)}% of your total listening time, with {round(total_minutes, 2)} minutes combined."
        }
    # END DEAL WITH PERCENTAGE QUESTIONS
    
    # ******************TODO: make this more dynamic? Returns false data******************
    # BEGIN REJECTION OF UNSUPPORTED QUESTIONS
    if any(term in question for term in ["genre", "rap", "hip hop", "pop", "rock"]):
        return {
            "answer": "I don't have genre information in your listening history."
        }
    
    if "least" in question:
        return {
            "answer": "I don't currently support finding least-listened artists."
        }
    # END REJECTION OF UNSUPPORTED QUESTIONS

    # BEGIN CHECK FOR SIMPLE QUESTIONS
    # Checks to see if question has already been computed in DASHBOARD_RESULT, so run_analysis_query() can be skipped
    if "top artist" in question:
        top = DASHBOARD_RESULT.get("topArtist", {})
        if top.get("name"):
            return {
                "answer": f"Your top artist is {top['name']} with {round(top['minutes'], 2)} minutes."
            }

    if "top song" in question:
        top = DASHBOARD_RESULT.get("topSongMin", {})
        if top.get("name"):
            return {
                "answer": f"Your top song is {top['name']} with {round(top['minutes'], 2)} minutes."
            }

    if "total listening" in question or "total minutes" in question:
        total = DASHBOARD_RESULT.get("totalListeningTime", {})
        if total.get("minutes") is not None:
            return {
                "answer": f"You listened to {round(total['minutes'], 2)} minutes of music."
            }
        
    if "top day" in question:
        top = DASHBOARD_RESULT.get("topDay", {})
        if top.get("full_date"):
            return {
                "answer": f"Your top day was {top['full_date']} with {round(top['minutes'], 2)} minutes."
            }
    if "top month" in question:
        top = DASHBOARD_RESULT.get("topMonth", {})
        if top.get("month"):
            return {
                "answer": f"Your top month was {top['month']} with {round(top['minutes'], 2)} minutes."
            }
    # END CHECK FOR SIMPLE QUESTIONS
    # ******************TODO: make this more dynamic? Returns false data******************
    
    # BEGIN MAIN PLANNER PROMPT
    # Convert user question into structured JSON for run_analysis_query()
    planner_prompt = f"""
    You convert Spotify listening questions into JSON analysis plans.

    Return ONLY valid JSON.

    Available group_by values:
    - artist
    - track
    - weekday
    - month
    - year
    - date

    Available metric values:
    - minutes
    - plays

    Available filters:
    - artist
    - year
    - month
    - weekday
    - date
    - start_date
    - end_date

    Rules:
    - Return JSON only.
    - Do not write Python.
    - Do not explain.
    - Do not perform calculations yourself.
    - Only use numbers provided in the computed result.
    - Use actual JSON null, not the string "null".
    - Use null for unknown or unused filters.
    - limit should usually be 10.
    - Include filter keys with null when they are unused.
    - Only create plans for questions supported by the available group_by, metric, and filters.
    - If the user gives a specific date like 8/2/2025, July 10 2025, 2025-08-02, or "August 8th", put it in filters.date as YYYY-MM-DD.
    - If the user asks for a specific date, exact date, "what date", "which date", "specific day", or "exact day", use group_by: "date".
    - Do NOT use group_by: "weekday" unless the user asks for a day of week, like Monday, Tuesday, weekend, or weekday.
    - If the question contains "between", "from", or a date range using "and" or "-", NEVER use filters.date. Use filters.start_date and filters.end_date in YYYY-MM-DD format.
    - If the user asks for more than one grouped result, use type: "multi_aggregation".
    - If the user asks for a total over a date range AND a top artist/song/day in that same range, use type: "multi_aggregation" and apply the same start_date/end_date filters to every query.

    Examples:

    Question: What was my top song and top artist on 5/26/2025?
    {{
    "type": "multi_aggregation",
    "queries": [
        {{
        "group_by": "track",
        "metric": "minutes",
        "limit": 1,
        "filters": {{
            "artist": null,
            "year": null,
            "month": null,
            "weekday": null,
            "date": "2025-05-26",
            "start_date": null,
            "end_date": null
        }}
        }},
        {{
        "group_by": "artist",
        "metric": "minutes",
        "limit": 1,
        "filters": {{
            "artist": null,
            "year": null,
            "month": null,
            "weekday": null,
            "date": "2025-05-26",
            "start_date": null,
            "end_date": null
        }}
        }}
    ]
    }}

    Question: What specific day did I listen to Ed Sheeran the most?
    {{
    "group_by": "date",
    "metric": "minutes",
    "limit": 1,
    "filters": {{
        "artist": "Ed Sheeran",
        "year": null,
        "month": null,
        "weekday": null,
        "date": null,
        "start_date": null,
        "end_date": null
    }}
    }}

    Question: How many minutes did I listen between 5/26/2025 and 5/30/2025 and who was my top artist?
    {{
    "type": "multi_aggregation",
    "queries": [
        {{
        "group_by": "date",
        "metric": "minutes",
        "limit": 10,
        "filters": {{
            "artist": null,
            "year": null,
            "month": null,
            "weekday": null,
            "date": null,
            "start_date": "2025-05-26",
            "end_date": "2025-05-30"
        }}
        }},
        {{
        "group_by": "artist",
        "metric": "minutes",
        "limit": 1,
        "filters": {{
            "artist": null,
            "year": null,
            "month": null,
            "weekday": null,
            "date": null,
            "start_date": "2025-05-26",
            "end_date": "2025-05-30"
        }}
        }}
    ]
    }}

    Question: How many minutes did I listen to music between 7/12/2025 and 7/16/2025?
    {{
    "group_by": "date",
    "metric": "minutes",
    "limit": 10,
    "filters": {{
        "artist": null,
        "year": null,
        "month": null,
        "weekday": null,
        "date": null,
        "start_date": "2025-07-12",
        "end_date": "2025-07-16"
    }}
    }}

    Question: How many minutes did I listen to music on 8/2/2025?
    {{
    "group_by": "artist",
    "metric": "minutes",
    "limit": 10,
    "filters": {{
        "artist": null,
        "year": null,
        "month": null,
        "weekday": null,
        "date": "2025-08-02",
        "start_date": null,
        "end_date": null
    }}
    }}

    Question: Who was my top artist?
    {{
    "group_by": "artist",
    "metric": "minutes",
    "limit": 10,
    "filters": {{
        "artist": null,
        "year": null,
        "month": null,
        "weekday": null,
        "date": null,
        "start_date": null,
        "end_date": null
    }}
    }}

    Question: What songs did I listen to most in 2023?
    {{
    "group_by": "track",
    "metric": "minutes",
    "limit": 10,
    "filters": {{
        "artist": null,
        "year": 2023,
        "month": null,
        "weekday": null,
        "date": null,
        "start_date": null,
        "end_date": null
    }}
    }}

    Question: What day do I listen to Ed Sheeran the most?
    {{
    "group_by": "weekday",
    "metric": "minutes",
    "limit": 7,
    "filters": {{
        "artist": "Ed Sheeran",
        "year": null,
        "month": null,
        "weekday": null,
        "date": null,
        "start_date": null,
        "end_date": null
    }}
    }}

    User question:
    {question}
    """
    # END MAIN PLANNER PROMPT

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
        return {"answer": "I could not understand that question as an analysis plan. Try rephrasing it."}

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

    # BEGIN EXPLANATION PROMPT
    explanation_prompt = f"""
    You are a Spotify listening history analyst.

    The user asked:
    {question}

    Python computed this result:
    {json.dumps(analysis_result, indent=2)}

    Answer directly and briefly.

    Rules:
    - Start with the direct answer.
    - Use only the computed result.
    - Do not speculate or infer missing information.
    - Do not say "I ran a query" or mention an "analysis plan".
    - Do not output JSON.
    - Keep the answer under 10 sentences.
    - If the result is empty, say: "I couldn't find any listening history matching that question."
    - If the question asks for total listening time, use total_minutes as the main answer.
    - If the result contains multiple queries, answer each part clearly.
    - Only answer the current question.
    - Do not assume context from previous questions.
    - Do not mention filters unless necessary.
    - If the question asks about genres and genre data is not available, say: "I don't have genre information in your listening history."
    - Do not infer or guess genres from artist names.
    """
    # END EXPLANATION PROMPT

    explanation_response = ollama.chat(
        model="qwen2.5:14b",
        messages=[{"role": "user", "content": explanation_prompt}]
    )

    return {"answer": explanation_response["message"]["content"]}

if __name__ == "__main__":
    app.run(debug=True)