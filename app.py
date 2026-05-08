from flask import Flask, request, render_template
import json
from analysis import calculateListeningStats
import ollama

LISTENING_HISTORY = []

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_files():
    global LISTENING_HISTORY
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

    LISTENING_HISTORY = all_entries
    result = calculateListeningStats(all_entries, start_date=start_date, end_date=end_date)
    return render_template("results.html", result=result)

@app.route("/llm")
def llm_page():
    return render_template("llm.html")

@app.route("/ask-llm", methods=["POST"])
def ask_llm():
    data = request.get_json()
    question = data["question"]

    history = LISTENING_HISTORY[:200]

    prompt = f"""
        You are a Spotify listening history analyst.

        Answer the user's question using their listening data.
        Be specific and mention artists, songs, and patterns.

        User question:
        {question}

        Listening history:
        {json.dumps(history)}
    """

    response = ollama.chat(
        model="llama3.2",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return {"answer": response["message"]["content"]}

if __name__ == "__main__":
    app.run(debug=True)