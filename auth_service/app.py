from flask import Flask, render_template, request, flash, url_for, redirect, jsonify, make_response
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import os
from dotenv import load_dotenv
import datetime
import jwt
from flask_cors import CORS
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer

load_dotenv()

app=Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.getenv('SECRET_KEY')

#mysqlconfiguration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_PORT'] = 3306
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD']=os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = 'nic_auth_service'

#mailconfiguration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

mail = Mail(app)
s = URLSafeTimedSerializer(app.secret_key)

#mysql initialization
mysql = MySQL(app)

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method =='POST':
        try:
            username = request.form['username']
            email = request.form['email']
            pwd = request.form['password']
            hashed_pwd = generate_password_hash(pwd)

            cur = mysql.connection.cursor()
            cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username,email,))
            user = cur.fetchone()

            if user:
                mysql.connection.commit()
                flash("User already exists with username or email", 'error')
                return render_template('register.html')

            cur.execute("insert into users (username, email, password) VALUES (%s, %s, %s)", (username, email, hashed_pwd))
            mysql.connection.commit()
            cur.close()
            flash("Registered successfully", 'success')
            return redirect(url_for('home'))
        except Exception as e:
            flash(f"Error: {e}", 'error')
            return render_template('register.html')
    else:
        return render_template('register.html')
    
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method =='POST':
        try:
            username=request.form['username']
            password=request.form['password']

            cur=mysql.connection.cursor()
            cur.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            cur.close()

            if user and check_password_hash(user[2], password):
                token = jwt.encode({
                    'user_id': user[0],
                    'username': user[1],
                    'exp': datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=5)
                }, os.getenv('SECRET_KEY'), algorithm='HS256')
                redirect_url = f"http://localhost:5001?token={token}"
                return redirect(redirect_url)
            else:
                flash("Invalid email or password", 'error')
                return redirect(url_for('home'))
        except Exception as e:
            flash(f"Error: {e}", 'error')
            return redirect(url_for('home'))
    return redirect(url_for('home'))

@app.route('/start_reset_password', methods=['GET', 'POST'])
def start_reset_password():
    return render_template('reset_email.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        try:
            email = request.form['email']
            token = s.dumps(email, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            msg = Message('Password Reset Request', sender='nic@exclusiveidvalidators.com', recipients=[email])
            msg.body = f'To reset your password, click the following link: {reset_url}'
            mail.send(msg)
            flash('A password reset link has been sent to your email.', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            flash(f"Error: {e}",'error')
            return redirect(url_for('home'))
    flash('Error', 'error')
    return redirect(url_for('home'))
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=3600)
    except:
        flash('The password reset link is invalid or has expired.','error')
        return redirect(url_for('home'))

    if request.method == 'POST':
        try:
            password = request.form['password']
            password_confirm = request.form['password_confirm']
            if password != password_confirm:
                flash('Passwords do not match.','error')
                return redirect(url_for('reset_password', token=token))
            hashed_pwd = generate_password_hash(password)
            cur=mysql.connection.cursor()
            cur.execute("""
                UPDATE users
                SET password = %s
                WHERE email = %s;
            """, (hashed_pwd, email))

            mysql.connection.commit()
            cur.close()
            flash('Your password has been updated!', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            flash(f"Error: {e}", 'error')
            return redirect(url_for('reset_password', token=token))

    return render_template('reset.html', token=token)

    
# @app.route('/logout', methods=['GET','POST'])
# def logout():
#     resp = make_response()
#     return resp

if  __name__ == '__main__':
    app.run(debug = True,port=5000)