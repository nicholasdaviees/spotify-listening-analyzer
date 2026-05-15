from collections import defaultdict
from datetime import datetime
import difflib

# BEGIN HELPER FUNCTIONS
def ms_to_min(ms):
    return ms / 60000

def ms_to_hours(ms):
    return ms / 3600000

def ms_to_days(ms):
    return ms / 86400000

def has_filter(filters, key):
    # Available filters: artist, track, year, month, weekday, date, start_date, end_date
    # Example: 
        # "filters": {{
        #    "artist": "Ed Sheeran",
        #    "year": null,
        #    "month": null,
        #    "weekday": null,
        #    "date": null
        # }}

    value = filters.get(key)
    return value not in [None, "", "null", "None", "unknown"]

def parse_entry(entry):
    artist = entry.get("artistName")
    track = entry.get("trackName")
    ms = entry.get("msPlayed", 0)
    end_time = entry.get("endTime")

    dt = None
    if end_time:
        try:
            dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M")
        except Exception:
            pass

    return artist, track, ms, dt
# END HELPER FUNCTIONS

def compute_artist_percentage(dashboard_result, artist_name):
    total_minutes = dashboard_result["totalListeningTime"]["minutes"]
    artist_totals = dashboard_result["allArtists"]["artist_totals"]

    matches = difflib.get_close_matches(artist_name, artist_totals.keys(), n=1, cutoff=0.8)

    if not matches:
        return {
            "error": f"I couldn't find an artist matching '{artist_name}'."
        }

    matched_artist = matches[0]

    artist_minutes = ms_to_min(artist_totals.get(matched_artist, 0))

    if total_minutes == 0:
        artist_percentage = 0
    else:
        artist_percentage = round((artist_minutes / total_minutes) * 100, 2)

    return {
        "artist": matched_artist,
        "minutes": artist_minutes,
        "total": total_minutes,
        "percent": artist_percentage
    }

def run_analysis_query(raw_listening_history, plan):
    # Read analysis plan
    group_by = plan.get("group_by", "artist")
    metric = plan.get("metric", "minutes")
    limit = plan.get("limit", 10)
    filters = plan.get("filters", {})
    sort_order = plan.get("sort", "desc")

    results = {}

    # BEGIN FOR LOOP PROCESSING LISTENING HISTORY
    for entry in raw_listening_history:
        artist, track, ms, dt = parse_entry(entry) # Example: ["Drake", "God's Plan", 210000, datetime(2025, 7, 12, 14, 30)]

        # Removes 0ms plays from all analysis
        if ms <= 0:
            continue

        # Error handling
        if not artist and group_by == "artist":
            continue

        if not track and group_by == "track":
            continue
        
        # BEGIN FILTERS
        # Date filter
        if has_filter(filters, "date") and dt:
            if dt.strftime("%Y-%m-%d") != filters["date"]:
                continue

        # Year filter
        if has_filter(filters, "year") and dt:
            if dt.year != int(filters["year"]):
                continue

        # Month filter
        if has_filter(filters, "month") and dt:
            month_value = filters["month"] # Could be name or number (e.g., "July" or "7")

            if isinstance(month_value, str):
                try:
                    # Turn name into number (e.g., "July" into 7)
                    # Handles full names and abbreviations
                    month_number = datetime.strptime(month_value[:3], "%b").month
                except Exception:
                    continue
            else:
                month_number = int(month_value)

            if dt.month != month_number:
                continue

        # Weekday filter
        if has_filter(filters, "weekday") and dt:
            if dt.strftime("%A").lower() != filters["weekday"].lower():
                continue

        # Artist filter
        if has_filter(filters, "artist"):
            query_artist = filters["artist"].lower()
            actual_artist = artist.lower() if artist else ""

            similarity = difflib.SequenceMatcher(None, query_artist, actual_artist).ratio() # Fuzzy matching

            if similarity < 0.7:
                continue

        # Track filter
        if has_filter(filters, "track"):
            query_track = filters["track"].lower()
            actual_track = track.lower() if track else ""

            similarity = difflib.SequenceMatcher(None, query_track, actual_track).ratio()

            if similarity < 0.7:
                continue
        
        # Date range filter
        if has_filter(filters, "start_date") and has_filter(filters, "end_date") and dt:
            start_date = filters["start_date"]
            end_date = filters["end_date"]

            # Fixes reveresed dates
            if start_date > end_date:
                start_date, end_date = end_date, start_date

            date_str = dt.strftime("%Y-%m-%d")

            # Range inclusive with start and end dates
            if not (start_date <= date_str <= end_date):
                continue
        # END FILTERS

        if group_by == "artist":
            key = artist
        elif group_by == "track":
            key = track
        elif group_by == "weekday":
            key = dt.strftime("%A") if dt else "Unknown"
        elif group_by == "month":
            key = dt.strftime("%B %Y") if dt else "Unknown"
        elif group_by == "year":
            key = str(dt.year) if dt else "Unknown"
        elif group_by == "date":
            key = dt.strftime("%B %-d, %Y") if dt else "Unknown"
        else:
            key = artist

        # Initialize or update key entry in results
        if key not in results:
            results[key] = {
                "plays": 0,
                "ms": 0
            }

        results[key]["plays"] += 1
        results[key]["ms"] += ms
    # END FOR LOOP PROCESSING LISTENING HISTORY

    output = []

    # Create ouput list
    for key, value in results.items():
        output.append({
            group_by: key,
            "plays": value["plays"],
            "minutes": round(ms_to_min(value["ms"]), 2)
        })

    reverse_sort = sort_order != "asc"

    if metric == "plays":
        output.sort(key=lambda x: x["plays"], reverse=reverse_sort)
    else:
        output.sort(key=lambda x: x["minutes"], reverse=reverse_sort)

    total_minutes = round(ms_to_min(sum(value["ms"] for value in results.values())), 2)

    return {
        "total_minutes": total_minutes,
        "results": output[:limit]
    }

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
        "allArtists": {
            "artist_totals": dict(artist_totals)
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
            "full_date": top_day[0].strftime("%B %d, %Y"),
            "weekday": top_day[0].strftime("%a").upper(),
            "day": top_day[0].day,
            "minutes": ms_to_min(top_day[1]),
            "hours": ms_to_hours(top_day[1])
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
            "month": datetime.strptime(top_month[0], "%Y-%m").strftime("%B %Y"),
            "minutes": ms_to_min(top_month[1]),
            "percentage": (top_month[1] / total_listening_time_ms) * 100 if total_listening_time_ms else 0
        }
    }

    return result