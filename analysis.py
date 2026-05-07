from collections import defaultdict
from datetime import datetime

def ms_to_min(ms):
    return ms / 60000

def ms_to_hours(ms):
    return ms / 3600000

def ms_to_days(ms):
    return ms / 86400000

def calculateListeningStats(listeningHistory, start_date=None, end_date=None):
    total_listening_time_ms = 0
    artist_totals = defaultdict(int)
    song_total_ms = defaultdict(int)
    song_total_count = defaultdict(int)
    day_totals = defaultdict(int)
    month_totals = defaultdict(int)
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

    for entry in listeningHistory:
        artist = entry.get("artistName", "").strip()
        track = entry.get("trackName", "").strip()
        end_time = entry.get("endTime")
        ms_played = entry.get("msPlayed", 0)

        if not artist or not track or not end_time:
            continue

        date = datetime.strptime(end_time, "%Y-%m-%d %H:%M")
        entry_date = date.date()

        if start_date_obj and entry_date < start_date_obj:
            continue
        if end_date_obj and entry_date > end_date_obj:
            continue

        # Calculate total listening time
        total_listening_time_ms += ms_played

        # Calculate artist totals
        artist_totals[artist] += ms_played

        # Calculate song totals
        song_key = f"{artist} - {track}"
        song_total_ms[song_key] += ms_played
        song_total_count[song_key] += 1

        # Calculate day totals
        date = datetime.strptime(end_time, "%Y-%m-%d %H:%M")
        day_key = date.date()
        day_totals[day_key] += ms_played

        # Calculate month totals
        month_key = date.strftime("%Y-%m")
        month_totals[month_key] += ms_played

    top_artist = max(artist_totals.items(), key=lambda x: x[1], default=(None, 0))
    top_song = max(song_total_ms.items(), key=lambda x: x[1], default=(None, 0))
    top_day = max(day_totals.items(), key=lambda x: x[1], default=(None, 0))
    top_month = max(month_totals.items(), key=lambda x: x[1], default=(None, 0))

    result = {
        "topArtist": {
            "name": top_artist[0],
            "minutes": ms_to_min(top_artist[1])
        },
        "topSongMin": {
            "name": top_song[0],
            "minutes": ms_to_min(top_song[1])
        },
        "topSongCount": {
            "name": top_song[0],
            "count": song_total_count[top_song[0]]
        },
        "topDay": {
            "full_date": top_day[0].strftime("%m-%d-%Y"),
            "weekday": top_day[0].strftime("%a").upper(),
            "day": top_day[0].day,
            "minutes": ms_to_min(top_day[1])
        },
        "totalListeningTime": {
            "minutes": ms_to_min(total_listening_time_ms),
            "hours": ms_to_hours(total_listening_time_ms),
            "days": ms_to_days(total_listening_time_ms)
        },
        "monthlyListeningTime": {
            month: ms_to_min(ms)
            for month, ms in month_totals.items()
        },
        "topMonth": {
            "month": datetime.strptime(top_month[0], "%Y-%m").strftime("%b %Y"),
            "minutes": ms_to_min(top_month[1]),
            "percentage": (top_month[1] / total_listening_time_ms) * 100 if total_listening_time_ms else 0
        }
    }

    return result