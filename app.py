
from flask import Flask, render_template, request, session, redirect, url_for
from flask_session import Session
import re
import json
import random
from datetime import datetime, timedelta
import urllib.parse
import difflib

app = Flask(__name__)
app.secret_key = 'hotelbotsecretkey'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

def parse_message(message):
    city_match = re.search(r'in (\w+)', message.lower())
    city = city_match.group(1).lower() if city_match else "goa"

    date_range_match = re.search(r'from (\d{1,2})[a-z]{0,2}\s+([a-z]+)(?:\s+\d{4})?\s*(?:to|till|until|-)\s*(\d{1,2})[a-z]{0,2}\s+([a-z]+)', message.lower())
    days_stay_match = re.search(r'for (\d+) (day|days|night|nights)', message.lower())

    if date_range_match:
        start_day = int(date_range_match.group(1))
        start_month = date_range_match.group(2)
        end_day = int(date_range_match.group(3))
        end_month = date_range_match.group(4)

        checkin = datetime.strptime(f"{start_day} {start_month} 2025", "%d %B %Y")
        checkout = datetime.strptime(f"{end_day} {end_month} 2025", "%d %B %Y")
    else:
        checkin = datetime.today()
        if days_stay_match:
            days = int(days_stay_match.group(1))
            checkout = checkin + timedelta(days=days)
        else:
            checkout = checkin + timedelta(days=1)

    people_match = re.search(r'(\d+)\s+(adult|person|people)', message.lower())
    adults = people_match.group(1) if people_match else "1"

    return city, checkin.strftime("%Y-%m-%d"), checkout.strftime("%Y-%m-%d"), adults

@app.route('/', methods=['GET'])
def index():
    if 'chat' not in session or not session['chat']:
        session['chat'] = [{'sender': 'bot', 'text': '👋 How can I help you today?'}]
    return render_template('index.html', chat_history=session['chat'])

@app.route('/chat', methods=['POST'])
def chat():
    message = request.form['message']
    session['chat'].append({'sender': 'user', 'text': message})

    city, checkin, checkout, adults = parse_message(message)

    with open("all_mock_hotels_updated.json", "r") as mf:
        all_hotels_dict = json.load(mf)
        all_hotels = all_hotels_dict.get(city.lower(), [])

    if "book" in message.lower() or "details" in message.lower() or "contact" in message.lower():
        hotel_names = [hotel["hotel"]["name"].lower() for hotel in all_hotels]
        matches = difflib.get_close_matches(message.lower(), hotel_names, n=1, cutoff=0.4)
        if matches:
            for hotel in all_hotels:
                if hotel["hotel"]["name"].lower() == matches[0]:
                    query = urllib.parse.quote_plus(hotel["hotel"]["name"] + " " + city)
                    gmaps = f"https://www.google.com/maps/search/{query}"
                    gsearch = f"https://www.google.com/search?q={query}"
                    bot_text = f"""🔍 Here’s what I found for *{hotel['hotel']['name']}*:
📍 <a href='{gmaps}' target='_blank'>Map</a> | 🔗 <a href='{gsearch}' target='_blank'>Search</a>

Can I help you with something else? 😊"""
                    session['chat'].append({'sender': 'bot', 'text': bot_text})
                    return redirect(url_for('index'))

    city_hotels = all_hotels_dict.get(city.lower(), [])
    if not city_hotels:
        session['chat'].append({'sender': 'bot', 'text': f"😕 Sorry, unable to find hotels in {city.title()}."})
        return redirect(url_for('index'))

    valid_hotels = random.sample(city_hotels, min(len(city_hotels), random.randint(2, 5)))

    reply = f"""Absolutely! Here's what I found in {city.upper()} from 📅 {checkin} to {checkout} for 👤 {adults}:
"""
    for h in valid_hotels:
        name = h['hotel']['name']
        price = h['offers'][0]['price']['total']
        currency = h['offers'][0]['price']['currency']
        desc = h['offers'][0]['room']['description']['text']
        reply += f"""
🏨 *{name}*
💰 {price} {currency}/night
🛏 {desc[:60]}... 😌
-----------------------------"""

    reply += """
Let me know if you'd like help with anything else! 😊
"""
    session['chat'].append({'sender': 'bot', 'text': reply})

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
