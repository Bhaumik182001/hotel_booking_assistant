from flask import Flask, render_template, request, session, redirect, url_for
from flask_session import Session
from amadeus import Client, ResponseError
import re, json, random, difflib, urllib.parse
from datetime import datetime, timedelta

app = Flask(__name__)

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_COOKIE_NAME"] = "session"  
app.secret_key = 'hotelbotsecretkey'

Session(app)

amadeus = Client(
    client_id='sCOmmNEtwAS3Lr7qHrej4RVAaf6eYWeu',
    client_secret='XMqv0QKJIfgMEPIF'
)

city_map = {
    'delhi': 'DEL', 'goa': 'GOI', 'mumbai': 'BOM', 'bangalore': 'BLR', 'hyderabad': 'HYD',
    'chennai': 'MAA', 'kolkata': 'CCU', 'jaipur': 'JAI', 'lucknow': 'LKO', 'ahmedabad': 'AMD',
    'pune': 'PNQ', 'nagpur': 'NAG', 'kochi': 'COK', 'coimbatore': 'CJB', 'indore': 'IDR',
    'bhubaneswar': 'BBI', 'guwahati': 'GAU', 'surat': 'STV', 'rajkot': 'RAJ', 'amritsar': 'ATQ',
    'varanasi': 'VNS', 'vizag': 'VTZ', 'trivandrum': 'TRV', 'mysore': 'MYQ', 'aurangabad': 'IXU',
    'dehradun': 'DED', 'ranchi': 'IXR', 'jodhpur': 'JDH', 'ludhiana': 'LUH', 'jalandhar': 'IXJ',
    'patiala': 'IXC', 'bathinda': 'BUP', 'mohali': 'IXC', 'firozpur': 'IXC', 'hoshiarpur': 'IXC',
    'pathankot': 'IXP', 'fazilka': 'IXC', 'barnala': 'IXC', 'mansa': 'IXC', 'sangrur': 'IXC',
    'kapurthala': 'IXC', 'london': 'LON', 'newyork': 'NYC', 'dubai': 'DXB', 'paris': 'PAR',
    'tokyo': 'TYO', 'sydney': 'SYD', 'singapore': 'SIN', 'toronto': 'YTO'
}

def parse_message(message):
    city_match = re.search(r'in (\w+)', message.lower())
    city_word = city_match.group(1).lower() if city_match else 'goa'

    # fuzzy city match
    fuzzy_city = difflib.get_close_matches(city_word, list(city_map.keys()), n=1, cutoff=0.6)
    if fuzzy_city:
        print(f"🧠 Fuzzy matched '{city_word}' to '{fuzzy_city[0]}'")
        city_word = fuzzy_city[0]

    city = city_map.get(city_word, 'GOI')

    # Check for date range
    range_match = re.search(r'from (\d{1,2})\w*\s+([A-Za-z]+).*?(?:to|till|-).*?(\d{1,2})\w*\s+([A-Za-z]+)', message)
    duration_match = re.search(r'for (\d+)\s*(day|days|night|nights|week|weeks|month|months|year|years)', message.lower())

    if range_match:
        d1, m1, d2, m2 = range_match.groups()
        checkin = datetime.strptime(f"{d1} {m1} 2025", "%d %B %Y")
        checkout = datetime.strptime(f"{d2} {m2} 2025", "%d %B %Y")
    else:
        checkin = datetime.today()
        if duration_match:
            num, unit = int(duration_match.group(1)), duration_match.group(2)
            if "week" in unit:
                stay_length = num * 7
            elif "month" in unit:
                stay_length = num * 30
            elif "year" in unit:
                stay_length = num * 365
            else:
                stay_length = num
        else:
            stay_length = 1
        checkout = checkin + timedelta(days=stay_length)

    people = re.search(r'(\d+)\s+(adult|person|people)', message.lower())
    adults = people.group(1) if people else "1"

    return city, checkin.strftime("%Y-%m-%d"), checkout.strftime("%Y-%m-%d"), adults, city_word

@app.route("/", methods=["GET"])
def index():
    if "chat" not in session or not session["chat"]:
        session["chat"] = [{"sender": "bot", "text": "👋 How can I help you today?"}]
    return render_template("index.html", chat_history=session["chat"])

@app.route("/chat", methods=["POST"])
def chat():
    message = request.form["message"]
    # Clear chat if user asks to reset
    reset_phrases = ["clear", "reset", "start over", "begin again", "start from beginning"]
    if any(phrase in message.lower() for phrase in reset_phrases):
        session["chat"] = [{"sender": "bot", "text": "👋 How can I help you today?"}]
        return redirect(url_for("index"))
    session["chat"].append({"sender": "user", "text": message})
    include_links = "book" in message.lower()

    city, checkin, checkout, adults, city_word = parse_message(message)

    valid_hotels = []
    city_mock = []

    try:
        with open("sample.json") as mf:
            all_hotels = json.load(mf)
            city_mock = all_hotels.get(city_word.lower(), [])
            print(f"🧪 Loaded {len(city_mock)} mock hotels for {city_word.lower()}")
    except Exception as e:
        print("❌ Error loading mock data:", e)

    try:
        print(f"🌐 Searching for hotels in {city}")
        hotel_resp = amadeus.reference_data.locations.hotel.get(
            keyword=city_word,
            subType='HOTEL_GDS',
            view='FULL',
            radius=50,
            radiusUnit='KM'
        )
        hotel_ids = [h["hotelId"] for h in hotel_resp.data if "hotelId" in h]
        print(f"🔗 Found hotel IDs: {hotel_ids}")

        for hid in hotel_ids[:50]:
            try:
                offer = amadeus.shopping.hotel_offers_search.get(
                    hotelIds=hid,
                    checkInDate=checkin,
                    checkOutDate=checkout,
                    adults=adults
                )
                if offer.data:
                    valid_hotels.extend(offer.data)
            except Exception:
                continue
    except Exception as e:
        print("❌ Amadeus API error:", e)

    if len(valid_hotels) < 2 and city_mock:
        print("⚠️ Fallback triggered. Using mock data.")
        supplement = random.sample(city_mock, min(5, len(city_mock)))
        valid_hotels.extend(supplement)
        random.shuffle(valid_hotels)

    
    
    # Filter by feature keyword if present in message
    feature_keywords = ["sea view", "balcony", "breakfast", "bathtub", "wifi", "netflix", "smart tv", "pool", "desk", "air conditioning", "garden", "city view", "mini fridge", "rain shower", "lounge", "hardwood", "soundproof"]
    requested_feature = None
    for keyword in feature_keywords:
        if keyword in message.lower():
            requested_feature = keyword
            print(f"🔍 Filtering hotels by feature: {requested_feature}")
            break

    if requested_feature:
        valid_hotels = [h for h in valid_hotels if requested_feature in h["offers"][0]["room"]["description"]["text"].lower()]

    # Sorting preference extraction
    sort_by = None
    if any(w in message.lower() for w in ["low to high", "cheapest", "price", "cost"]):
        sort_by = "price"
    elif any(w in message.lower() for w in ["rating", "best rated", "top rated"]):
        sort_by = "rating"
    elif any(w in message.lower() for w in ["most features", "more features", "detailed"]):
        sort_by = "features"

    # Sort hotels
    if sort_by == "price":
        valid_hotels.sort(key=lambda h: float(h["offers"][0]["price"]["total"]))
    elif sort_by == "rating":
        valid_hotels.sort(key=lambda h: h.get("rating", 0), reverse=True)
    elif sort_by == "features":
        valid_hotels.sort(key=lambda h: len(h["offers"][0]["room"]["description"]["text"].split(",")), reverse=True)


    if not valid_hotels and city_mock:
        print("🔁 API gave no result. Using only mock data.")
        valid_hotels = random.sample(city_mock, min(5, len(city_mock)))

    if not valid_hotels:
        session["chat"].append({"sender": "bot", "text": f"😞 Sorry, I couldn't find any hotels in {city}."})
        return redirect(url_for("index"))

    if any(word in message.lower() for word in ["book", "details", "contact"]):
        names = [h["hotel"]["name"].lower() for h in valid_hotels if "hotel" in h]
        match = difflib.get_close_matches(message.lower(), names, n=1, cutoff=0.4)
        if match:
            for h in valid_hotels:
                if h["hotel"]["name"].lower() == match[0]:
                    q = urllib.parse.quote_plus(h["hotel"]["name"] + " " + city_word)
                    maps = f"https://www.google.com/maps/search/{q}"
                    search = f"https://www.google.com/search?q={q}"
                    msg = f"\n🔍 Found <b>*{h['hotel']['name']}*</b>\n📍 <a href='{maps}'>Map</a> | 🔗 <a href='{search}'>Search</a>\nCan I help you with anything else?"
                    
                    session["chat"].append({"sender": "bot", "text": msg})
                    return redirect(url_for("index"))

    reply = f"\n✨ Here are some great options in {city_word.title()} from 📅 {checkin} to {checkout} for 👤 {adults}:\n"
    for h in valid_hotels[:random.randint(3, 5)]:
        name = h["hotel"]["name"]
        price = h["offers"][0]["price"]["total"]
        currency = h["offers"][0]["price"]["currency"]
        desc_text = h["offers"][0]["room"]["description"]["text"]

        reply += f"\n🏨 <b style='font-size: 1.1em;'>{name}</b> ⭐ {h.get('rating', 'N/A')}/5"
        reply += f"\n💰 <i>{price} {currency}/night</i>"
        reply += f"\n✨ <u>Features:</u>"

        lines = [d.strip() for d in re.split(r'[,.]', desc_text) if d.strip()]
        for line in lines:
            emoji = "📌"
            lower = line.lower()
            if "balcony" in lower: emoji = "🌅"
            elif "breakfast" in lower: emoji = "🍳"
            elif "bathtub" in lower: emoji = "🛁"
            elif "wifi" in lower: emoji = "📶"
            elif "tv" in lower or "netflix" in lower: emoji = "📺"
            elif "workspace" in lower or "desk" in lower: emoji = "💼"
            elif "view" in lower: emoji = "🏞️"
            elif "pool" in lower: emoji = "🏊"
            elif "king" in lower or "queen" in lower: emoji = "🛏️"
            elif "ac" in lower or "air conditioning" in lower: emoji = "❄️"
            desc_line = f"{emoji} {line.strip()}"
            reply += f"\n{desc_line}"

        if include_links:
            q = urllib.parse.quote_plus(name + " " + city_word)
            maps = f"https://www.google.com/maps/search/{q}"
            search = f"https://www.google.com/search?q={q}"
            reply += f"\n🔗 <a href='{search}'>Search</a> | <a href='{maps}'>Map</a>"

        reply += "\n---------------------"
    session["chat"].append({"sender": "bot", "text": reply})
    return redirect(url_for("index"))

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
