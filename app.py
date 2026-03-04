import json

file_path = "listeningHistoryData/StreamingHistory_music_0.json"

with open(file_path, 'r') as file:
    data = json.load(file)

for entry in data:
    artist = entry["artistName"]
    song = entry["trackName"]
    ms = entry["msPlayed"]

    print(f"Artist: {artist}\n")
    print(f"Song: {song}\n")
    print(f"Minutes Played: {ms / 60000:.2f} minutes\n\n")