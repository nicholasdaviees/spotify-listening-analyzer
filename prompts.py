import json

def get_artist_percentage_intent_prompt(question, conversation_context=""):
    return f"""
        Classify this Spotify listening-history question.

        Return ONLY valid JSON.

        Possible intents:
        - artist_percentage
        - other

        Rules:
        - Only use artist_percentage if the CURRENT question asks for percent, percentage, share, portion, or fraction of listening from one or more artists.
        - Do NOT use artist_percentage just because the conversation context contains a previous percentage answer.
        - If the CURRENT question asks about hours, minutes, plays, top song, top track, "that song", or listening time for a song, return {{"intent": "other"}}.
        - For artist_percentage, extract artist names into an artists list.
        - Use the conversation context only to resolve references like him, her, them, that artist, or it.

        Conversation context:
        {conversation_context}

        Use the conversation context to resolve references like:
        - him
        - her
        - them
        - that artist
        - that song
        - that date
        - it
        - then
        - that period
        - same time

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

def get_clarity_prompt(question):
    return f"""
        Is this a meaningful Spotify listening-history question?

        Return ONLY "yes" or "no".

        Say "yes" if the question asks about:
        - top artists or songs
        - listening time (minutes or hours)
        - plays
        - a specific artist
        - a specific song
        - a specific date or date range
        - follow-up questions using words like "him", "that artist", "that song", "then"

        Say "no" only if the question is:
        - random text
        - unrelated to Spotify listening history
        - too vague to answer even with context

        Important:
        - Follow-up questions like "what was my top song from him?" are VALID and should return "yes".

        Question:
        {question}
    """

def get_planner_prompt(question, conversation_context=""):
    return f"""
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

        Conversation context:
        {conversation_context}

        Use the conversation context only to resolve follow-up references.

        Rules:
        - Return JSON only.
        - Do not write Python.
        - Do not explain.
        - Do not perform calculations yourself.
        - Only use numbers provided in the computed result.
        - Use actual JSON null, not the string "null".
        - Use null for unknown or unused filters.
        - limit should usually be 10.
        - If the user asks to "list all", "show all", or "everything", override limit and set it to 100.
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

def get_clarification_prompt(question):
    return f"""
        You are helping a user ask better questions about their Spotify listening history.

        The user asked:
        {question}

        Explain briefly why the question is unclear in a friendly, conversational way, and suggest 2-3 better questions the user can ask.

        You MUST only suggest questions that this system can answer, such as:
        - top artists or songs
        - listening time (minutes or hours)
        - listening on a specific date
        - listening between dates
        - listening by a specific artist

        Rules:
        - Be friendly and conversational.
        - Do NOT sound critical or formal.
        - Do NOT mention JSON, code, or analysis plans.
        - Do NOT suggest generic or meta questions (like "what can you do").
        - Give concrete, specific example questions.
        - Keep it under 3 sentences.

        Example style:
        "I'm not sure what you're looking for. Try asking something like:
        - 'Who are my top artists?'
        - 'How many minutes did I listen to music?'"

        Examples of GOOD suggestions:
        - "Who are my top artists?"
        - "How many minutes did I listen to Ed Sheeran?"
        - "What songs did I listen to on 5/26/2025?"

        Examples of BAD suggestions:
        - "What can you help me with?"
        - "Tell me about my data"
    """

def get_explanation_prompt(question, analysis_result):
    return f"""
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
        - If the result is empty, explain briefly why the question could not be understood, and suggest 2-3 better ways to ask it, giving concrete example questions.
        - If the question asks for total listening time, use total_minutes as the main answer.
        - If the result contains multiple queries, answer each part clearly.
        - Only answer the current question.
        - Do not assume context from previous questions.
        - Do not mention filters unless necessary.
        - If the question asks about genres and genre data is not available, say: "I don't have genre information in your listening history."
        - Do not infer or guess genres from artist names.
    """