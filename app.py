from flask import Flask, request, jsonify, render_template
import json

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_files():
    files = request.files.getlist("jsonFiles")
    all_data = []

    for file in files:
        try:
            data = json.load(file)
            all_data.append({
                "filename": file.filename,
                "content": data
            })
        except Exception as e:
            all_data.append({
                "filename": file.filename,
                "error": str(e)
            })

    for song in data:
        print(f"Song: {song['trackName']} by {song['artistName']}")

    return jsonify(all_data)

if __name__ == "__main__":
    app.run(debug=True)