from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory , jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import requests
from datetime import datetime, timedelta
import re
from google import genai
from google.genai import types
import json

travel_ai_client = genai.Client(api_key="AIzaSyCafGTbLM5feh2Kv09c_gBxaXNNu096gtI")

intel_client = genai.Client(api_key="AIzaSyAnI65AxC9dTBIlYhdBpnI3cKLCg8L6_1w")

conv_client  = genai.Client(api_key="AIzaSyC6Ap3HcaAupnqIKN-uxyfs63YP0d3MJao")

sos_client = genai.Client(api_key = "AIzaSyArTa-SBVVc_KFXhhA620u16ST7wbTB5iY")

packing_client = genai.Client(api_key ="AIzaSyBQjG-J5bnhLCVcpZDHiDBphs_sEnkUfx0")

app = Flask(__name__)
app.secret_key = 'CHANGE_THIS_TO_SOMETHING_SECRET'  # Important for security

# --- Configuration ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'travel.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(basedir, 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)

# --- Login Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirect here if user isn't logged in

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    bio = db.Column(db.String(500), default="Ready for the next adventure!")
    currency = db.Column(db.String(10), default="USD")
    avatar = db.Column(db.String(100), default="default.png")
    trips = db.relationship('Trip', backref='owner', lazy=True)


class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    origin = db.Column(db.String(100), nullable=True)
    destination = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    budget = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Planned')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Link to User

    # Relationships
    expenses = db.relationship('Expense', backref='trip', lazy=True, cascade="all, delete-orphan")
    activities = db.relationship('Activity', backref='trip', lazy=True, cascade="all, delete-orphan")
    tasks = db.relationship('Task', backref='trip', lazy=True, cascade="all, delete-orphan")
    documents = db.relationship('Document', backref='trip', lazy=True, cascade="all, delete-orphan")
    journal_entries = db.relationship('JournalEntry', backref='trip', lazy=True)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(20), nullable=True)
    type = db.Column(db.String(50))
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(200), nullable=False)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)

# Make sure this import is at the very top of app.py
import requests

# Replace your old get_weather_data function with this one:
def get_weather_data(city):
    try:
        # 1. Get Coordinates (Latitude/Longitude) from OpenStreetMap
        # We need a User-Agent header so OpenStreetMap doesn't block us
        headers = {'User-Agent': 'WanderlustApp/1.0'}
        geo_url = f"https://nominatim.openstreetmap.org/search?q={city}&format=json&limit=1"

        geo_response = requests.get(geo_url, headers=headers)
        geo_data = geo_response.json()

        if not geo_data:
            return None  # City not found

        lat = geo_data[0]['lat']
        lon = geo_data[0]['lon']

        # 2. Get Weather from Open-Meteo (Free API, No Key needed)
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        weather_response = requests.get(weather_url)
        weather_data = weather_response.json()

        return weather_data.get('current_weather')

    except Exception as e:
        print(f"Weather Error: {e}")
        return None

def get_conversion_rate(target_currency):
    try:
        # Fetch rates with USD as the base (Assuming your app uses USD by default)
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url)
        data = response.json()
        return data['rates'].get(target_currency, 1.0)
    except:
        return 1.0
# Initialize DB
with app.app_context():
    db.create_all()

# --- Auth Routes ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # 🔒 1. PASSWORD STRENGTH VALIDATION
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return redirect(url_for('register'))
        if not re.search(r"[A-Z]", password):
            flash('Password must contain at least one uppercase letter.', 'danger')
            return redirect(url_for('register'))
        if not re.search(r"[a-z]", password):
            flash('Password must contain at least one lowercase letter.', 'danger')
            return redirect(url_for('register'))
        if not re.search(r"[0-9]", password):
            flash('Password must contain at least one number.', 'danger')
            return redirect(url_for('register'))
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            flash('Password must contain at least one special character (!@#$...).', 'danger')
            return redirect(url_for('register'))

        # 2. CHECK IF USER EXISTS
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose another.', 'warning')
            return redirect(url_for('register'))

        # 3. CREATE USER
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('🎉 Registration successful! Welcome to Wanderlust ', 'success')
        login_user(new_user)
        return redirect(url_for('profile'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # 1. Find User (SQL Version)
        user = User.query.filter_by(username=username).first()

        # 2. Check Password
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            # 3. Show Error
            flash('❌ Invalid username or password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- App Routes (Protected) ---

@app.route('/')
@login_required
def index():
    # Show ONLY the current user's trips
    trips = Trip.query.filter_by(user_id=current_user.id).order_by(Trip.start_date).all()
    total_budget = sum(trip.budget for trip in trips)
    return render_template('index.html', trips=trips, total_budget=total_budget, user=current_user)
# --- ROUTE: Add New Trip ---
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_trip():
    if request.method == 'POST':
        destination = request.form['destination']
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        budget = float(request.form['budget'])

        # Create the new trip object
        new_trip = Trip(
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            user_id=current_user.id  # Link the trip to the logged-in user
        )

        try:
            db.session.add(new_trip)
            db.session.commit()
            flash('✅ New trip added successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'❌ Error adding trip: {e}', 'danger')
            return redirect(url_for('add_trip'))

    return render_template('add.html')

@app.route('/view_trip/<int:id>')
@login_required
def view_trip(id):
    trip = Trip.query.get_or_404(id)

    # 1. Base Calculations (in USD)
    total_spent = sum(expense.amount for expense in trip.expenses)

    # 2. Currency Conversion Logic
    target_currency = request.args.get('currency', 'USD')
    rate = 1.0
    if target_currency != 'USD':
        rate = get_conversion_rate(target_currency)

    # Calculate Totals
    display_budget = trip.budget * rate
    display_spent = total_spent * rate

    # 3. Create a "Converted" List of Expenses for the Table
    # We create a new list of dictionaries so we don't change the actual database
    converted_expenses = []
    for exp in trip.expenses:
        converted_expenses.append({
            'name': exp.name,
            'category': exp.category,
            'amount': exp.amount * rate  # <--- Convert individual item
        })

    # 4. Prepare Chart Data (Using Converted Values)
    chart_data = {}
    for exp in converted_expenses:
        if exp['category'] in chart_data:
            chart_data[exp['category']] += exp['amount']
        else:
            chart_data[exp['category']] = exp['amount']

    # 5. Weather
    weather = get_weather_data(trip.destination)

    return render_template('details.html',
                         trip=trip,
                         total_spent=total_spent,
                         display_budget=display_budget,
                         display_spent=display_spent,
                         converted_expenses=converted_expenses, # <--- Passing the converted list
                         currency_symbol=target_currency,
                         chart_data=chart_data,
                         weather=weather)

@app.route('/delete/<int:id>')
@login_required
def delete_trip(id):
    trip = Trip.query.get_or_404(id)
    if trip.user_id != current_user.id:
        return "Unauthorized", 403

    # Delete files
    if trip.documents:
        for doc in trip.documents:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], doc.filepath))
            except: pass

    db.session.delete(trip)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/ai_planner', methods=['GET', 'POST'])
@login_required
def ai_planner():
    if request.method == 'POST':
        # 1. GET DATA SECURELY (Prevents 400 Bad Request)
        origin = request.form.get('origin')
        destination = request.form.get('destination')
        budget = request.form.get('budget')
        days = request.form.get('days')
        start_date_str = request.form.get('start_date')

        # 2. VALIDATE DATA
        if not destination or not budget or not days:
            flash("Please fill in all fields", "warning")
            return redirect(url_for('ai_planner'))

        # 3. BUILD THE PROMPT
        # We construct a detailed sentence for the AI using the form data
        user_prompt = f"Plan a {days}-day trip from {origin} to {destination} starting {start_date_str} with budget ${budget}."
        today = datetime.now().strftime('%Y-%m-%d')

        prompt_content = f"""
        You are an expert travel architect.
        Request: "{user_prompt}"
        Current Date: {today}

        CRITICAL INSTRUCTIONS:
        1. Return JSON ONLY.
        2. "activities" list must cover exactly {days} days.
        3. Day 1 MUST start with "Flight/Travel from {origin} to {destination}". Estimate realistic travel cost.
        4. Budget limit: {budget}.

        JSON STRUCTURE:
        {{
            "destination": "{destination}",
            "start_date": "{start_date_str}",
            "end_date": "YYYY-MM-DD",
            "budget": {budget},
            "activities": [
                {{"day": 1, "name": "Flight from {origin}", "type": "Transport", "time": "09:00", "cost": 450.0}},
                {{"day": 1, "name": "Check-in Hotel", "type": "Accommodation", "time": "14:00", "cost": 0}}
            ]
        }}
        """

        try:
            # 5. CALL AI (Using the retry logic is best, but direct call works too)
            response = travel_ai_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[prompt_content]
            )

            if not response.text:
                raise ValueError("AI returned empty response")

            # 6. PARSE & SAVE
            clean_text = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(clean_text)

            new_trip = Trip(
                origin=origin,
                destination=data['destination'],
                start_date=datetime.strptime(data['start_date'], '%Y-%m-%d'),
                end_date=datetime.strptime(data['end_date'], '%Y-%m-%d'),
                budget=float(data['budget']),
                status='Planned',
                user_id=current_user.id
            )
            db.session.add(new_trip)
            db.session.commit()

            # Save Activities
            trip_start = new_trip.start_date
            for act in data.get('activities', []):
                day_num = int(act.get('day', 1))
                # Calculate correct date
                act_date = trip_start + timedelta(days=day_num - 1)

                new_act = Activity(
                    name=act['name'],
                    type=act.get('type', 'Sightseeing'),
                    time=act.get('time', '09:00'),
                    date=act_date,
                    trip_id=new_trip.id
                )
                db.session.add(new_act)

                # Save Expense if cost > 0
                cost = float(act.get('cost', 0))
                if cost > 0:
                    new_exp = Expense(
                        name=act['name'],
                        amount=cost,
                        category=act.get('type', 'General'),
                        trip_id=new_trip.id
                    )
                    db.session.add(new_exp)

            db.session.commit()
            return redirect(url_for('view_trip', id=new_trip.id))

        except Exception as e:
            print(f"ERROR: {e}")
            flash("Something went wrong. Please try again.", "danger")
            return redirect(url_for('ai_planner'))

    return render_template('ai_planner.html')


@app.route('/trip/<int:id>/get_intel')
@login_required
def get_intel(id):
    trip = Trip.query.get_or_404(id)

    # Simple logic to guess the country from the city name
    # (In a real app, you'd ask the user for the country, but this works for major cities)
    # We ask Gemini to just give us the Country Name for the city to be accurate.
    try:
        # 1. Ask AI for the Country Name (to handle "Paris" -> "France")
        prompt = f"What country is {trip.destination} in? Return ONLY the country name."
        ai_resp = intel_client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
        country_name = ai_resp.text.strip()

        # 2. Call RestCountries API
        url = f"https://restcountries.com/v3.1/name/{country_name}?fullText=true"
        resp = requests.get(url)
        data = resp.json()[0]

        # 3. Extract Info
        intel = {
            "flag": data['flags']['svg'],
            "currency": list(data['currencies'].keys())[0],
            "language": list(data['languages'].values())[0],
            "timezone": data['timezones'][0],
            "maps_link": data['maps']['googleMaps']
        }
        return jsonify(intel)

    except Exception as e:
        print(f"Intel Error: {e}")
        return jsonify({"error": "Could not fetch data"})


@app.route('/trip/<int:id>/get_essentials')
@login_required
def get_essentials(id):
    trip = Trip.query.get_or_404(id)

    # Prompt Gemini for the "External Search" data
    prompt = f"""
    I am a tourist visiting {trip.destination}.
    Provide a JSON object with this exact info:
    {{
        "visa_policy": "Short summary of visa rules (e.g. Visa-free for 90 days)",
        "plug_type": "The plug type letter (e.g. Type G)",
        "voltage": "The voltage (e.g. 230V)",
        "tipping": "One sentence on tipping customs (e.g. 10% is standard)",
        "currency_code": "The 3-letter currency code (e.g. JPY)"
    }}
    Only return raw JSON.
    """

    try:
        response = conv_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[prompt],
        )
        return response.text
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/trip/<int:id>/add_journal', methods=['POST'])
@login_required
def add_journal(id):
    trip = Trip.query.get_or_404(id)
    content = request.form.get('content')

    if content:
        new_entry = JournalEntry(content=content, trip_id=trip.id)
        db.session.add(new_entry)
        db.session.commit()
        flash('📔 Diary entry added!', 'success')

    # Redirect back to the details page (preserving the currency if set)
    currency = request.args.get('currency', 'USD')
    return redirect(url_for('view_trip', id=trip.id, currency=currency))

# --- ROUTE: Public Shared Trip (Read-Only) ---
@app.route('/public/<int:id>')
def public_trip(id):
    trip = Trip.query.get_or_404(id)

    # We fetch weather for the visitor
    weather = get_weather_data(trip.destination)

    # We render a SPECIAL 'public_trip.html' template
    # This template will have NO edit buttons, NO forms, just data.
    return render_template('public_trip.html', trip=trip, weather=weather)

@app.route('/delete_activity/<int:id>')
@login_required
def delete_activity(id):
    activity = Activity.query.get_or_404(id)
    # Security Check: Ensure the current user actually owns this trip!
    if activity.trip.user_id == current_user.id:
        db.session.delete(activity)
        db.session.commit()
        flash('Activity removed.', 'info')
    return redirect(url_for('view_trip', id=activity.trip.id))

@app.route('/delete_expense/<int:id>')
@login_required
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    if expense.trip.user_id == current_user.id:
        db.session.delete(expense)
        db.session.commit()
        flash('Expense removed.', 'info')
    return redirect(url_for('view_trip', id=expense.trip.id))


@app.route('/trip/<int:trip_id>/edit_activity/<int:activity_id>', methods=['POST'])
@login_required
def edit_activity(trip_id, activity_id):
    activity = Activity.query.get_or_404(activity_id)

    # Security: Ensure ownership
    if activity.trip.user_id != current_user.id:
        return "Unauthorized", 403

    # Update fields
    activity.name = request.form['name']
    activity.type = request.form['type']
    activity.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    # Handle time (handle empty cases if necessary)
    if request.form['time']:
        activity.time = request.form['time']

    db.session.commit()
    flash('✅ Activity updated!', 'success')
    return redirect(url_for('view_trip', id=trip_id))


# --- ROUTE: Fetch Emergency SOS Numbers ---
@app.route('/trip/<int:id>/get_sos')
@login_required
def get_sos(id):
    trip = Trip.query.get_or_404(id)

    # Prompt AI for safety numbers
    prompt = f"""
    I am visiting {trip.destination}.
    Return a JSON object with the emergency phone numbers for: Police, Ambulance, Fire.
    Format: {{"Police": "100", "Ambulance": "102", "Fire": "101"}}
    Only return raw JSON.
    """

    try:
        response = sos_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[prompt],
        )
        return response.text
    except Exception as e:
        # Fallback to universal emergency number if AI fails
        print(f"SOS Error: {e}")
        return jsonify({"Police": "112", "Ambulance": "112", "Fire": "112"})

# --- ROUTE: Fetch Real-World Deals ---
@app.route('/trip/<int:id>/get_deals')
@login_required
def get_deals(id):
    trip = Trip.query.get_or_404(id)

    # Prompt: Ask for specific real-world packages
    prompt = f"""
    I am planning a trip to {trip.destination}.
    Suggest 3 distinct travel packages available on major websites (like MakeMyTrip, Expedia, Yatra, Thomas Cook).
    For each, provide:
    1. Title (e.g. "Romantic Paris Getaway")
    2. Provider (e.g. "MakeMyTrip")
    3. Approximate Price (e.g. "$1200 / ₹90,000")
    4. Key Inclusions (e.g. "Flights + 4 Star Hotel + Breakfast")

    Return ONLY a raw JSON array. Example:
    [
        {{
            "title": "Example Deal",
            "provider": "Expedia",
            "price": "$500",
            "inclusions": "Hotel + Flight",
            "search_term": "Paris vacation packages"
        }}
    ]
    """

    try:
        response = conv_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return jsonify({"error": str(e)})

# --- ROUTE: User Profile ---
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Update Text Info
        current_user.username = request.form.get('username')
        current_user.bio = request.form.get('bio')
        current_user.currency = request.form.get('currency')

        # Handle Avatar Upload
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.avatar = filename

        db.session.commit()
        flash('✅ Profile Updated!', 'success')
        return redirect(url_for('index'))

    # Calculate Stats
    trip_count = len(current_user.trips)
    total_spent = sum([sum([e.amount for e in t.expenses]) for t in current_user.trips])

    return render_template('profile.html', user=current_user, trip_count=trip_count, total_spent=total_spent)



@app.route('/discover')
def discover():
    # 1. Ask Gemini for RICH, detailed live data
    prompt = """
    You are a luxury travel analyst. Provide exactly 6 trending global travel destinations for the current season.
    Return ONLY a valid JSON array of objects. No markdown formatting, no backticks.
    Format exactly like this:
    [
      {
        "name": "Kyoto",
        "country": "Japan",
        "budget": "$$",
        "weather": "Mild",
        "activity": "Culture",
        "category": "Trending",
        "description": "Once the capital of Japan, Kyoto is a city on the island of Honshu. It's famous for its numerous classical Buddhist temples, as well as gardens, imperial palaces, Shinto shrines and traditional wooden houses.",
        "best_time": "March to May",
        "top_attractions": ["Fushimi Inari Taisha", "Kinkaku-ji", "Arashiyama Bamboo Grove"],
        "local_dish": "Kaiseki Ryori",
        "language": "Japanese"
      }
    ]
    """

    try:
        # Call Gemini (Adjust client name if yours is different)
        response = sos_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt
        )

        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        live_destinations = json.loads(clean_json)

        # 2. Fetch LIVE images from Unsplash
        UNSPLASH_ACCESS_KEY = "V_0zPJnutUJkXOEOPA9oreZTDEDCo_pIWm8dboZ9K1w" # Replace this!

        for dest in live_destinations:
            city_name = dest['name']
            unsplash_url = f"https://api.unsplash.com/search/photos?query={city_name} travel&client_id={UNSPLASH_ACCESS_KEY}&per_page=1&orientation=landscape"

            try:
                img_res = requests.get(unsplash_url).json()
                if img_res.get('results'):
                    dest['image'] = img_res['results'][0]['urls']['regular']
                else:
                    dest['image'] = "https://images.unsplash.com/photo-1488085061387-422e29b40080?w=800&q=80"
            except:
                dest['image'] = "https://images.unsplash.com/photo-1488085061387-422e29b40080?w=800&q=80"

        return render_template('discover.html', destinations=live_destinations)

    except Exception as e:
        print(f"Discovery Error: {e}")
        flash("Live uplink failed. Loading cached destination data.", "danger")
        # Fallback data if API fails
        fallback_dests = [{
            "name": "Kyoto", "country": "Japan", "budget": "$$", "weather": "Mild", "activity": "Culture", "category": "Trending",
            "description": "Famous for classical Buddhist temples, gardens, imperial palaces, and traditional wooden houses.",
            "best_time": "March to May", "top_attractions": ["Fushimi Inari", "Kinkaku-ji", "Arashiyama"],
            "local_dish": "Matcha & Kaiseki", "language": "Japanese",
            "image": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=800&q=80"
        }]
        return render_template('discover.html', destinations=fallback_dests)


# --- ROUTE: Auto-Generate Smart Packing List ---
@app.route('/trip/<int:id>/generate_packing', methods=['POST'])
@login_required
def generate_packing(id):
    trip = Trip.query.get_or_404(id)

    # Security check
    if trip.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    # 1. Clear any existing tasks for this trip to prevent duplicates
    for task in trip.tasks:
        db.session.delete(task)
    db.session.commit()

    # 2. Calculate trip duration
    days = (trip.end_date - trip.start_date).days
    if days <= 0: days = 1

    # 3. Prompt Gemini
    prompt = f"""
    You are a tactical travel preparation AI. Generate a smart, highly essential packing list for a {days}-day trip to {trip.destination}.
    Consider the likely weather and activities for this location.
    Return ONLY a raw JSON array of strings. Do not use markdown blocks.
    Keep it to exactly 10 crucial items.
    Example: ["Passport & Visas", "Universal Power Adapter", "Lightweight Rain Jacket", "Comfortable Walking Shoes"]
    """

    try:
        # Use your existing AI client
        response = packing_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[prompt]
        )

        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        items = json.loads(clean_json)

        # 4. Save to Database
        for item_name in items:
            new_task = Task(name=item_name, completed=False, trip_id=trip.id)
            db.session.add(new_task)

        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        print(f"Packing AI Error: {e}")
        return jsonify({'error': 'Failed to generate list'}), 500

# --- ROUTE: Toggle Packing Item Checkbox ---
@app.route('/task/<int:task_id>/toggle', methods=['POST'])
@login_required
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.trip.user_id == current_user.id:
        task.completed = not task.completed
        db.session.commit()
        return jsonify({'success': True, 'completed': task.completed})
    return jsonify({'error': 'Unauthorized'}), 403


@app.after_request
def add_header(response):

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers['Cache-Control'] = 'public, max-age=0'
    return response

if __name__ == "__main__":
    app.run(debug=True)