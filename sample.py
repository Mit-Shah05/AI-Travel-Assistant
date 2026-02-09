import json
import re
import random
from math import radians, sin, cos, sqrt, atan2
import sqlite3
from datetime import datetime



# Connect to SQLite DB
conn = sqlite3.connect("travel_memory.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trip_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    source TEXT,
    destination TEXT,
    days INTEGER,
    budget INTEGER,
    total_cost INTEGER,
    hotel TEXT,
    attractions TEXT
)
""")
conn.commit()


# Load Dataset
with open("travel_dataset.json", "r") as f:
    dataset = json.load(f)


# Airport coordinates (for flight estimation)
AIRPORTS = {
    "mumbai": {"lat": 19.0760, "lon": 72.8777},
    "delhi": {"lat": 28.6139, "lon": 77.2090},
    "paris": {"lat": 48.8566, "lon": 2.3522},
    "tokyo": {"lat": 35.6762, "lon": 139.6503},
    "dubai": {"lat": 25.2048, "lon": 55.2708},
    "london": {"lat": 51.5072, "lon": -0.1276},
    "rome": {"lat": 41.9028, "lon": 12.4964},
    "sydney": {"lat": -33.8688, "lon": 151.2093},
    "new york": {"lat": 40.7128, "lon": -74.0060}
}



# Memory (Conversation Context)
last_trip = {
    "source": None,
    "city": None,
    "budget": None,
    "days": None,
    "hotels": None,
    "selected_hotel": None,
    "chosen_attractions": None,
    "attractions_all": None
}


# PARSE USER INPUT
def parse_user_request(user_text):
    text = user_text.lower()

    # Extract source → destination (handles: from Mumbai to Rome under $4000)
    from_to = re.search(r"from\s+([a-z\s]+?)\s+to\s+([a-z\s]+?)(?:\s+under|\s+within|\s+budget|\s+max|$)", text)
    source = from_to.group(1).strip().title() if from_to else None
    destination = from_to.group(2).strip().title() if from_to else None


    # Extract budget
    budget_match = re.search(r"(?:under|within|max|budget)\s*\$?\s*(\d+)", text)
    budget = int(budget_match.group(1)) if budget_match else None

    # Extract trip duration
    days_match = re.search(r"(\d+)\s*(?:day|days)", text)
    days = int(days_match.group(1)) if days_match else 3

    # If destination not found via "to", fallback to dataset matching
    if destination is None:
        for c in dataset["cities"]:
            city_name = c["city"].lower()
            if re.search(rf"\b{city_name}\b", text):  # exact city match
                destination = c["city"]
                break
        

    return source, destination, days, budget



# Calculate Flight Distance + Estimated Cost
def calculate_flight_cost(source, destination):
    if not source or not destination:
        return None, 0

    if source.lower() not in AIRPORTS or destination.lower() not in AIRPORTS:
        return None, 0

    lat1 = radians(AIRPORTS[source.lower()]["lat"])
    lon1 = radians(AIRPORTS[source.lower()]["lon"])
    lat2 = radians(AIRPORTS[destination.lower()]["lat"])
    lon2 = radians(AIRPORTS[destination.lower()]["lon"])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance_km = 6371 * c

    # Long haul cheaper per km
    price_per_km = 0.08 if distance_km > 3000 else 0.12
    estimated_price = int(distance_km * price_per_km)

    return int(distance_km), estimated_price



# Generate Itinerary
def generate_itinerary(source, city, days, budget):
    global last_trip

    distance, flight_cost = calculate_flight_cost(source, city)
    remaining_budget = budget - flight_cost

    if city is None:
        return "Destination not recognized. Available cities: Paris, Rome, Tokyo, Dubai, London, Sydney."

    city_data = next((item for item in dataset["cities"] if item["city"].lower() == city.lower()), None)

    if city_data is None:
        return f"Destination '{city}' not found in dataset."

    hotels = city_data["hotels"]
    attractions = city_data["attractions"]

    # Use already chosen hotel if exists
    if last_trip.get("selected_hotel"):
        hotel = last_trip["selected_hotel"]
    else:
        # Select hotel <= 60% of remaining budget
        hotel_budget_cap = remaining_budget * 0.60
        viable_hotels = [h for h in hotels if h["price_per_night"] * days <= hotel_budget_cap]
        hotel = random.choice(viable_hotels) if viable_hotels else min(hotels, key=lambda h: h["price_per_night"])


    # Attractions (2/day)
    random.shuffle(attractions)
    selected_attractions = attractions[:days * 2]

    hotel_cost = hotel["price_per_night"] * days
    attraction_cost = sum(a["entry_fee"] for a in selected_attractions)
    misc_cost = int(remaining_budget * 0.15)
    total_cost = flight_cost + hotel_cost + attraction_cost + misc_cost
    # -------- Save Trip to DB (Memory) --------
    cursor.execute("""
    INSERT INTO trip_history (timestamp, source, destination, days, budget, total_cost, hotel, attractions)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source,
        city,
        days,
        budget,
        total_cost,
        hotel["name"],
        ", ".join([a["name"] for a in selected_attractions])
    ))
    conn.commit()


    # Save session
    last_trip.update({
        "source": source,
        "city": city,
        "budget": budget,
        "days": days,
        "hotels": hotels,
        "selected_hotel": hotel,
        "chosen_attractions": selected_attractions,
        "attractions_all": attractions.copy()
    })

    # Output
    output = f"""
✈️ Trip Itinerary
🌍 Route: {source} ➝ {city}
📅 Duration: {days} days
💰 Total Budget: ${budget}

🛫 Estimated Flight Cost: ${flight_cost} ({distance} km)
💵 Remaining After Flight: ${remaining_budget}

🏨 Hotel Selected: {hotel['name']} ({hotel['type']}) ⭐ {hotel['rating']}
📍 Location: {hotel['location']}
💵 Cost/Night: ${hotel['price_per_night']}
---
"""

    index = 0
    for day in range(1, days + 1):
        output += f"\nDay {day}\n"
        for _ in range(2):
            if index < len(selected_attractions):
                a = selected_attractions[index]
                output += f"- {a['name']} — ${a['entry_fee']} | {a['duration_hours']} hrs | Best time: {a['best_time_to_visit']}\n"
                index += 1
        output += "---\n"

    output += f"""
🔢 Cost Breakdown
✈️ Flights: ${flight_cost}
🏨 Hotel: ${hotel_cost}
🎡 Attractions: ${attraction_cost}
🚕 Food + Transport: ${misc_cost}

✅ Total Estimated Spend = ${total_cost}
➡️ Remaining Budget: ${budget - total_cost}
"""
    return output



# Follow-up Chat (hotel filtering, change attractions, choose new hotel)
def handle_follow_up(msg):
    msg = msg.lower()

    # Recall trip even after restart (from DB)
    if "show last" in msg or "previous" in msg or "last trip" in msg:
        cursor.execute("SELECT source, destination, days, budget FROM trip_history ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()

        if not row:
            return "No previous trips found in memory."

        # Restore memory state
        last_trip["source"], last_trip["city"], last_trip["days"], last_trip["budget"] = row

        return generate_itinerary(row[0], row[1], row[2], row[3])

    CATEGORY_MAP = {
        "shopping": ["Shopping"],
        "museum": ["Museum", "Cultural", "History"],
        "food": ["Food", "Food & Culture"],
        "sightseeing": ["Landmark", "Tour", "Nature", "Cultural"],
    }

    if not last_trip["city"]:
        return "Please plan a trip first."

    hotels = last_trip["hotels"]
    attractions = last_trip["attractions_all"]
    city = last_trip["city"]
    budget = last_trip["budget"]
    days = last_trip["days"]
    source = last_trip["source"]

    msg = msg.lower()

    # List hotels by category
    if "show" in msg and "hotel" in msg:
        if "luxury" in msg:
            filtered = [h for h in hotels if h["type"].lower() == "luxury"]
        elif "mid" in msg:
            filtered = [h for h in hotels if h["type"].lower() == "mid-range"]
        elif "budget" in msg:
            filtered = [h for h in hotels if h["type"].lower() == "budget"]
        else:
            return "Specify hotel type: luxury / mid / budget"

        last_trip["filtered_hotels"] = filtered

        response = "🛏️ Available hotels:\n"
        for i, h in enumerate(filtered, start=1):
            response += f"{i}. {h['name']} — ${h['price_per_night']} | ⭐ {h['rating']}\n"
        return response

    # Book / choose hotel
    if "choose" in msg or "book" in msg or "select" in msg:
        filtered = last_trip.get("filtered_hotels", [])
        index = re.search(r"(\d+)", msg)
        if index and filtered:
            idx = int(index.group(1)) - 1
            chosen = filtered[idx]
            last_trip["selected_hotel"] = chosen

            return generate_itinerary(source, city, days, budget)

        return "Choose a valid hotel option number."

    # Change attractions
    if any(cat in msg for cat in ["shopping", "museum", "food", "sightseeing"]):
        category = next(cat for cat in CATEGORY_MAP if cat in msg)
        matching = [a for a in attractions if any(x in a["category"] for x in CATEGORY_MAP[category])]

        day_num = int(re.search(r"day\s*(\d+)", msg).group(1)) if "day" in msg else random.randint(1, days)

        start = (day_num - 1) * 2
        last_trip["chosen_attractions"][start:start+2] = matching[:2]

        return generate_itinerary(last_trip["source"], last_trip["city"], last_trip["days"], last_trip["budget"])

    return "Try: show luxury hotels / change day 2 to shopping / choose hotel 2"



# Chat Loop
print("👋 Hey! I’m your Travel Assistant.")
print("Example: ➜ plan a 4 day trip from Mumbai to Paris under $5000")

while True:
    user_msg = input("\nYou: ")

    if user_msg.lower() in ["exit", "quit", "bye"]:
        print("👋 Goodbye!")
        break

    source, city, days, budget = parse_user_request(user_msg)

    if city and budget and source:
        print(generate_itinerary(source, city, days, budget))
    else:
        print(handle_follow_up(user_msg))
