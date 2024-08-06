from flask import Flask, request, flash, redirect, jsonify, render_template, make_response
from dotenv import load_dotenv
import os
import jwt
from flask_cors import CORS
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from flask_mysqldb import MySQL

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.getenv('SECRET_KEY')

app.config['UPLOAD_FOLDER'] = 'uploads/'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# MySQL configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_PORT'] = 3306
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = 'nic_user_service'

# MySQL initialization
mysql = MySQL(app)

counts = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366]
middle = 0

def calculateMonthDate(middle):
    for i in range(1, 13):
        month = 1
        day = middle - counts[-1]
        if middle <= counts[i]:
            month = i
            day = middle - counts[i - 1]
            break
    return month, day

def determineGender():
    global middle
    gender = "Male"
    if middle > 500:
        gender = "Female"
        middle = middle - 500
    return gender

def mainFunc(id):
    if id[-1] == "V":
        year = int("19" + id[0:2])
        middle = int(id[2:5])
        gender = determineGender()
        month, day = calculateMonthDate(middle)
        age = date.today().year - year
        dob = f"{day}/{month}/{year}"
        return [gender, dob, age]
    else:
        year = int(id[0:4])
        middle = int(id[4:7])
        gender = determineGender()
        month, day = calculateMonthDate(middle)
        age = date.today().year - year
        dob = f"{day}/{month}/{year}"
        return [gender, dob, age]

@app.route('/', methods=['GET', 'POST'])
def home():
    token = request.args.get('token')
    if token:
        try:
            decoded = jwt.decode(token, app.secret_key, algorithms=['HS256'])
            user_id = decoded['user_id']
            resp = make_response(render_template('dashboard.html', id=user_id))
            resp.set_cookie('token', token, httponly=True, samesite='Strict')
            return resp
        except jwt.ExpiredSignatureError:
            print('Expired token')
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            print('Invalid token')
            return jsonify({'error': 'Invalid token'}), 401
    return render_template('dashboard.html')

def save_file(file):
    if file and file.filename.endswith('.csv'):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        process_csv(file_path)

def process_csv(file_path):
    df = pd.read_csv(file_path, header=None)
    ids = df[0].tolist()
    print(ids)
    with ThreadPoolExecutor() as executor:
        for id in ids:
            
            executor.submit(process_id, id)

def process_id(id):
    print(id)
    with app.app_context():
        result = mainFunc(str(id))
        print(result)
        store_in_database(id, result)

def store_in_database(id, result):
    print(result, id)
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO nics (id, user_id, gender, dob, age)
            VALUES (%s, %s, %s, %s, %s)
        """, (str(id), 4, result[1], result[0], result[2]))
        mysql.connection.commit()
        cur.close()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    except Exception as e:
        print(f"Unexpected error: {e}")

@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
    if 'files' not in request.files:
        print('No file part')
        return render_template('dashboard.html')

    files = request.files.getlist('files')

    if not files:
        print('No selected file')
        return render_template('dashboard.html')

    with ThreadPoolExecutor(max_workers=len(files)) as executor:
        for file in files:
            executor.submit(save_file, file)

    print('Files uploaded successfully')
    return render_template('dashboard.html')

@app.route('/test', methods=['GET', 'POST'])
def test():
    result = ['Male', '9/8/2009', 15]
    id = "392174724V"
    store_in_database(id, result)
    return render_template('dashboard.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001)