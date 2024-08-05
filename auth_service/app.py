from flask import Flask, render_template, request, flash, session, url_for, redirect, jsonify, make_response
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import os
from dotenv import load_dotenv
import datetime
import jwt
from flask_cors import CORS

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

#mysql initialization
mysql = MySQL(app)

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method =='POST':
        username = request.form['username']
        email = request.form['email']
        pwd = request.form['password']
        hashed_pwd = generate_password_hash(pwd)

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cur.fetchone()

        if user:
            mysql.connection.commit()
            flash("User already exists with username.", 'error')
            return render_template('login.html')

        cur.execute("insert into users (username, email, password) VALUES (%s, %s, %s)", (username, email, hashed_pwd))
        mysql.connection.commit()
        cur.close()
        flash("Registered successfully", 'success')
        return render_template('login.html')
    else:
        return render_template('register.html')
    
@app.route('/login', methods=['GET','POST'])
def login():
    username=request.form['username']
    password=request.form['password']

    cur=mysql.connection.cursor()
    cur.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()

    if user and check_password_hash(user[2], password):
        token = jwt.encode({
            'user_id': user[0],
            'exp': datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=5)
        }, os.getenv('SECRET_KEY'), algorithm='HS256')
        redirect_url = f"http://localhost:5001?token={token}"
        return redirect(redirect_url)
    flash("Invalid email or password", 'error')
    print("error")
    return render_template('login.html')
    
@app.route('/logout')
def logout():
    session.pop('token', None)
    return redirect(url_for('home'))

if  __name__ == '__main__':
    app.run(debug = True,port=5000)