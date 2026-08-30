from flask import Flask, request, render_template, session, redirect
import requests
import time
import ssl
import socket
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.secret_key = 'webhealth-secret-key-change-later'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class CheckHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    url = db.Column(db.String(300), nullable=False)
    response_time_ms = db.Column(db.Integer)
    hsts = db.Column(db.Boolean)
    x_frame_options = db.Column(db.Boolean)
    csp = db.Column(db.Boolean)
    ssl_days_left = db.Column(db.Integer)
    checked_at = db.Column(db.DateTime, default=datetime.now)

def check_response_time(url):
    start = time.time()
    response = requests.get(url)
    end = time.time()
    time_taken = round((end - start) * 1000)
    return time_taken

def check_security_headers(url):
    response = requests.get(url)
    headers = response.headers
    results = {
        "HSTS": "Strict-Transport-Security" in headers,
        "X-Frame-Options": "X-Frame-Options" in headers,
        "Content-Security-Policy": "Content-Security-Policy" in headers
    }
    return results

def check_ssl_expiry(hostname):
    context = ssl.create_default_context()
    with socket.create_connection((hostname, 443)) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as ssock:
            cert = ssock.getpeercert()
            expiry_str = cert['notAfter']
            expiry_date = datetime.strptime(expiry_str, '%b %d %H:%M:%S %Y %Z')
            days_left = (expiry_date - datetime.now()).days
            return days_left

@app.route('/')
def home():
    return "Website Health Checker is running!"

@app.route('/check')
def check_website():
    url = request.args.get('url')
    if not url:
        return "Please provide a URL, like /check?url=https://google.com"

    hostname = url.replace('https://', '').replace('http://', '').split('/')[0]

    response_time = check_response_time(url)
    headers_result = check_security_headers(url)
    ssl_days_left = check_ssl_expiry(hostname)

    return {
        "url": url,
        "response_time_ms": response_time,
        "security_headers": headers_result,
        "ssl_expiry_days_left": ssl_days_left
    }

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return {"error": "Email already registered"}, 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = User(name=name, email=email, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    return {"message": "Signup successful!"}, 201

@app.route('/signup-page')
def signup_page():
    return render_template('signup.html')

@app.route('/login-page')
def login_page():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user:
        return {"error": "User not found"}, 404

    if not bcrypt.check_password_hash(user.password, password):
        return {"error": "Incorrect password"}, 401

    session['user_id'] = user.id
    session['user_name'] = user.name

    return {"message": f"Welcome back, {user.name}!"}, 200

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login-page')

    history = CheckHistory.query.filter_by(user_id=session['user_id']).order_by(CheckHistory.checked_at.desc()).limit(10).all()

    return render_template('dashboard.html', user_name=session['user_name'], history=history)

@app.route('/check-and-save', methods=['POST'])
def check_and_save():
    if 'user_id' not in session:
        return {"error": "Please log in first"}, 401

    data = request.get_json()
    url = data.get('url')
    if not url:
        return {"error": "Please provide a URL"}, 400

    try:
        hostname = url.replace('https://', '').replace('http://', '').split('/')[0]
        response_time = check_response_time(url)
        headers_result = check_security_headers(url)
        ssl_days_left = check_ssl_expiry(hostname)
    except Exception as e:
        return {"error": f"Could not check this URL: {str(e)}"}, 400

    new_check = CheckHistory(
        user_id=session['user_id'],
        url=url,
        response_time_ms=response_time,
        hsts=headers_result['HSTS'],
        x_frame_options=headers_result['X-Frame-Options'],
        csp=headers_result['Content-Security-Policy'],
        ssl_days_left=ssl_days_left
    )
    db.session.add(new_check)
    db.session.commit()

    return {
        "url": url,
        "response_time_ms": response_time,
        "hsts": headers_result['HSTS'],
        "x_frame_options": headers_result['X-Frame-Options'],
        "csp": headers_result['Content-Security-Policy'],
        "ssl_days_left": ssl_days_left,
        "checked_at": new_check.checked_at.strftime('%d %b %Y, %I:%M %p')
    }, 200

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login-page')

if __name__ == '__main__':
    app.run(debug=True)
