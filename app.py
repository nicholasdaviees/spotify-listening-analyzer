from flask import Flask, request, jsonify, render_template
import json
from analysis import calculateListeningStats

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_files():
    files = request.files.getlist("jsonFiles")
    all_entries = []

    for file in files:
        try:
            data = json.load(file)
            if isinstance(data, list):
                all_entries.extend(data) # list of 
            else:
                print(f"{file.filename} is not a list")

        except Exception as e:
            print(f"Error reading {file.filename}: {e}")

    result = calculateListeningStats(all_entries)
    print(f"Top Artist is: {result['topArtist']['name']} with a total listening time of {result['topArtist']['minutes']:.2f} minutes")
    print(f"Top Song is: {result['topSongMin']['name']} with a total listening time of {result['topSongMin']['minutes']:.2f} minutes. That's {result['topSongCount']['count']} plays!")
    print(f"Top Day is: {result['topDay']['date']} with a total listening time of {result['topDay']['minutes']:.2f} minutes")
    print(f"Total Listening Time (min): {result['totalListeningTime']:.2f}")

    return jsonify(all_entries)

if __name__ == "__main__":
    app.run(debug=True)