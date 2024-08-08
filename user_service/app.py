from flask import Flask, request, flash,session,url_for, redirect, jsonify, render_template, make_response
from dotenv import load_dotenv
import os
import jwt
from flask_cors import CORS
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from flask_mysqldb import MySQL
import requests

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
def calculateMonthDate(middle):
    for i in range(1, 13):
        month = 1
        day = middle - counts[-1]
        if middle <= counts[i]:
            month = i
            day = middle - counts[i - 1]
            break
    return month, day, middle

def determineGender(middle):
    gender = "Male"
    if middle > 500:
        gender = "Female"
        middle = middle - 500
    return gender, middle

def mainFunc(id):
    global middle
    if id[-1] == "V":
        year = int("19" + id[0:2])
        middle = int(id[2:5])
        gender, middle = determineGender(middle)
        month, day, middle = calculateMonthDate(middle)
        age = date.today().year - year
        dob = f"{day}/{month}/{year}"
        return [gender, dob, age]
    else:
        year = int(id[0:4])
        middle = int(id[4:7])
        gender, middle = determineGender(middle)
        month, day, middle = calculateMonthDate(middle)
        age = date.today().year - year
        dob = f"{day}/{month}/{year}"
        return [gender, dob, age]
    
# def count_users(user_id):
#     cur = mysql.connection.cursor()
#     cur.execute("""
#     SELECT
#         COUNT(CASE WHEN gender = 'Male' THEN 1 END) AS male_count,
#         COUNT(CASE WHEN gender = 'Female' THEN 1 END) AS female_count
#     FROM nics
#     WHERE user_id = %s;
#     """, (user_id,))
#     counts = cur.fetchall()
#     cur.close()
#     session['Male']=counts[0][0]
#     session['Female']=counts[0][1]

    
def fetchData(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT nic, gender, dob, age, id FROM nics WHERE user_id = %s", (user_id,))
    session['details'] = cur.fetchall()
    session['selectedGender'] = 'All'
    cur.close()

@app.route('/setGender', methods=['GET', 'POST'])
def setSelectedGender():
    session['selectedGender'] = request.args.get('gender')
    return redirect(url_for('dashboard'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'token' in request.cookies:
        return render_template('dashboard.html')
    return redirect("http://localhost:5000/")

@app.route('/', methods=['GET', 'POST'])
def home():
    # session['details']=[]
    token = None
    if 'token' in request.cookies:
        # token = request.cookies.get('token')
        return redirect(url_for('dashboard'))
    else:
        token = request.args.get('token')
    if token:
        try:
            decoded = jwt.decode(token, app.secret_key, algorithms=['HS256'])
            user_id = decoded['user_id']
            fetchData(user_id)
            resp = make_response(redirect(url_for('dashboard')))
            resp.set_cookie('token', token, httponly=True, samesite='Strict')
            return resp
        except jwt.ExpiredSignatureError:
            flash('User session expired','error')
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            flash('Invalid token','error')
            return jsonify({'error': 'Invalid token'}), 401
    return redirect("http://localhost:5000/")

def save_file(file, user_id, username):
    if file and file.filename.endswith('.csv'):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"user_{username}_{file.filename}")
        file.save(file_path)
        process_csv(file_path, user_id)

def process_csv(file_path, user_id):
    df = pd.read_csv(file_path, header=None)
    ids = df[0].tolist()
    with ThreadPoolExecutor() as executor:
        for id in ids:
            executor.submit(process_id, id, user_id)

def process_id(id, user_id):
    with app.app_context():
        result = mainFunc(str(id))
        store_in_database(id, result, user_id)

def store_in_database(id, result, user_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO nics (nic, user_id, dob, gender, age)
            VALUES (%s, %s, %s, %s, %s)
        """, (str(id), user_id, result[1], result[0], result[2]))
        mysql.connection.commit()
        cur.close()
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'error')
    except Exception as e:
        flash(f"Unexpected error: {e}", 'error')

@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
    token = request.cookies.get('token')
    if not token:
        flash('User cannot be validated','error')
        return redirect("http://localhost:5000/")
    else:
        try:
            decoded = jwt.decode(token, app.secret_key, algorithms=['HS256'])
            user_id = decoded['user_id']
            username = decoded['username']
        except jwt.ExpiredSignatureError:
            flash('User session expired','error')
            return redirect("http://localhost:5000/")
        except jwt.InvalidTokenError:
            flash('Invalid token','error')
            return redirect("http://localhost:5000/")
    if 'files' not in request.files:
        flash('No file part','error')
        return redirect(url_for('dashboard'))

    files = request.files.getlist('files')

    if not files:
        flash('No file selected','error')
        return redirect(url_for('dashboard'))

    with ThreadPoolExecutor(max_workers=len(files)) as executor:
        for file in files:
            executor.submit(save_file, file, user_id, username)

    flash('Files uploaded successfully','success')
    fetchData(user_id)
    return redirect(url_for('dashboard'))

@app.route('/logout', methods=['GET'])
def logout():
    # auth_logout_url = "http://localhost:5000/logout"
    # response = requests.get(auth_logout_url)
    # if response.status_code == 200:
        session.pop('details', None)
        resp = make_response(redirect("http://localhost:5000/"))
        resp.delete_cookie('token')
        return resp
    # else:
    #     print("Error while logging out")
    #     return redirect(url_for('dashboard'))

@app.route('/delete', methods=['GET'])
def delete_row():
    id = request.args.get('id')
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM nics WHERE id = %s", (id,))
    mysql.connection.commit()
    cur.close()
    token = request.cookies.get('token')
    if not token:
        flash('User cannot be validated','error')
        return redirect("http://localhost:5000/")
    else:
        try:
            decoded = jwt.decode(token, app.secret_key, algorithms=['HS256'])
            user_id = decoded['user_id']
        except jwt.ExpiredSignatureError:
            flash('User session expired','error')
            return redirect("http://localhost:5000/")
        except jwt.InvalidTokenError:
            flash('Invalid token','error')
            return redirect("http://localhost:5000/")
    fetchData(user_id)
    flash('Row deleted successfully','success')
    return redirect(url_for('dashboard'))

@app.route('/download/csv', methods=['GET'])
def download_csv():
    if 'details' not in session or 'selectedGender' not in session:
        return jsonify({"error": "No data available"}), 400

    selected_gender = session['selectedGender']
    details = [detail for detail in session['details'] if selected_gender == 'All' or detail[1] == selected_gender]
    filtered_details = [(detail[0], detail[2], detail[1], detail[3]) for detail in details]
    df = pd.DataFrame(filtered_details, columns=['NIC', 'DOB', 'Gender', 'Age'])

    response = make_response(df.to_csv(index=False))
    response.headers["Content-Disposition"] = f"attachment; filename=user_data_{selected_gender}.csv"
    response.headers["Content-Type"] = "text/csv"
    return response

@app.route('/download/excel', methods=['GET'])
def download_excel():
    if 'details' not in session or 'selectedGender' not in session:
        return jsonify({"error": "No data available"}), 400

    selected_gender = session['selectedGender']
    details = [detail for detail in session['details'] if selected_gender == 'All' or detail[1] == selected_gender]
    filtered_details = [(detail[0], detail[2], detail[1], detail[3]) for detail in details]
    df = pd.DataFrame(filtered_details, columns=['NIC', 'DOB', 'Gender', 'Age'])

    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='UserData')
    writer._save()
    output.seek(0)

    response = make_response(output.read())
    response.headers["Content-Disposition"] = f"attachment; filename=user_data_{selected_gender}.xlsx"
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response

@app.route('/download/pdf', methods=['GET'])
def download_pdf():
    if 'details' not in session or 'selectedGender' not in session:
        return jsonify({"error": "No data available"}), 400

    selected_gender = session['selectedGender']
    details = [detail for detail in session['details'] if  selected_gender == 'All' or detail[1] == selected_gender]
    filtered_details = [(detail[0], detail[2], detail[1], detail[3]) for detail in details]
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=letter)
    width, height = letter
    y = height - 40

    c.drawString(30, y, "NIC")
    c.drawString(130, y, "DOB")
    c.drawString(230, y, "Gender")
    c.drawString(330, y, "Age")

    for detail in filtered_details:
        y -= 20
        c.drawString(30, y, str(detail[0]))
        c.drawString(130, y, str(detail[1]))
        c.drawString(230, y, str(detail[2]))
        c.drawString(330, y, str(detail[3]))

    c.save()
    output.seek(0)

    response = make_response(output.read())
    response.headers["Content-Disposition"] = f"attachment; filename=user_data_{selected_gender}.pdf"
    response.headers["Content-Type"] = "application/pdf"
    return response
    

@app.route('/test', methods=['GET', 'POST'])
def test():
    result = ['Male', '9/8/2009', 15]
    id = "392174724V"
    store_in_database(id, result)
    return render_template('dashboard.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001)