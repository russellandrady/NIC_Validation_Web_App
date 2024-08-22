from flask import Flask, request, flash,session,url_for, redirect, render_template, make_response
from dotenv import load_dotenv
import os
import jwt
from flask_cors import CORS
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from flask_mysqldb import MySQL
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
import re

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
    if re.fullmatch(r'\d{9}[vV]', id):
        year = int("19" + id[0:2])
        middle = int(id[2:5])
        gender, middle = determineGender(middle)
        if middle < 0 or middle > 366:
            return ["invalid nic", "invalid mid number", 0]
        month, day, middle = calculateMonthDate(middle)
        age = date.today().year - year
        if age < 15:
            return ["invalid nic", "too young", 0]
        dob = f"{day}/{month}/{year}"
        return [gender, dob, age]
    elif re.fullmatch(r'\d{12}', id):
        year = int(id[0:4])
        middle = int(id[4:7])
        gender, middle = determineGender(middle)
        if middle < 0 or middle > 366:
            return ["invalid nic", "invalid mid number", 0]
        month, day, middle = calculateMonthDate(middle)
        age = date.today().year - year
        if age < 15:
            return ["invalid nic", "too young", 0]
        dob = f"{day}/{month}/{year}"
        return [gender, dob, age]
    else:
        return ["invalid nic", "invalid structure", 0]
    
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
    if 'details' not in session:
        session['details'] = []
    
    current_details = cur.fetchall()
    
    new_details = [detail for detail in current_details if detail not in session['details']]
    
    session['temp_details'] = new_details
    
    session['details'] = current_details

    session['temp_details'] = new_details
    print(session['temp_details'])
    session['selectedGender'] = 'All'
    session['success_upload']=False
    cur.close()

@app.route('/setGender', methods=['GET', 'POST'])
def setSelectedGender():
    try:
        session['selectedGender'] = request.args.get('gender')
    except Exception as e:
        flash(f"Error: {e}", 'error')
        redirect(url_for('dashboard'))
    return redirect(url_for('dashboard'))

@app.route('/uploads', methods=['GET', 'POST'])
def dashboard():
    try:
        if 'token' in request.cookies:
            return render_template('dashboard.html')
        return redirect("http://localhost:5000/")
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect("http://localhost:5000/")

@app.route('/charts', methods=['GET', 'POST'])
def charts():
    try:
        if 'details' in session:
            return render_template('charts.html')
        return redirect("http://localhost:5000/")
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect("http://localhost:5000/")

@app.route('/', methods=['GET', 'POST'])
def home():
    try:
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
                return redirect("http://localhost:5000/")
            except jwt.InvalidTokenError:
                flash('Invalid token','error')
                return redirect("http://localhost:5000/")
        return redirect("http://localhost:5000/")
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect("http://localhost:5000/")

def save_file(file, user_id, username):
    if file and file.filename.endswith('.csv'):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"user_{username}_{file.filename}")
        file.save(file_path)
        process_csv(file_path, user_id)

def process_csv(file_path, user_id):
    df = pd.read_csv(file_path, header=None)
    ids = df[0].tolist()
    os.remove(file_path)
    with ThreadPoolExecutor() as executor:
        for id in ids:
            id = id.strip()
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
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO temp_nics (nic, user_id, dob, gender, age)
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
    try:
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
        if len(files) > 4:
            flash('Maximum 4 files can be uploaded at a time','error')
            return redirect(url_for('dashboard'))
        for file in files:
            if not file.filename.endswith('.csv'):
                flash('Only CSV files are allowed','error')
                return redirect(url_for('dashboard'))

        with ThreadPoolExecutor(max_workers=len(files)) as executor:
            for file in files:
                executor.submit(save_file, file, user_id, username)

        flash('Files uploaded successfully','success')
        fetchData(user_id)
        session['success_upload']=True
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect(url_for('dashboard'))

@app.route('/logout', methods=['GET'])
def logout():
    # auth_logout_url = "http://localhost:5000/logout"
    # response = requests.get(auth_logout_url)
    # if response.status_code == 200:
        try:
            session.pop('details', None)
            session.pop('temp_details', None)
            session.pop('success_upload', None)
            resp = make_response(redirect("http://localhost:5000/"))
            resp.delete_cookie('token')
            return resp
        except Exception as e: 
            flash(f"Error: {e}", 'error')
            return redirect(url_for('dashboard'))
    # else:
    #     print("Error while logging out")
    #     return redirect(url_for('dashboard'))

@app.route('/delete', methods=['GET'])
def delete_row():
    try:
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
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect(url_for('dashboard'))

@app.route('/download/csv', methods=['POST'])
def download_csv():
    try:
        data = request.json
        if not data or 'details' not in data:
            flash('No data available', 'error')
            return redirect(url_for('dashboard'))

        details = data['details']
        filtered_details = [(detail['nic'], detail['dob'], detail['gender'], detail['age']) for detail in details]
        df = pd.DataFrame(filtered_details, columns=['NIC', 'Gender', 'DOB', 'Age'])

        response = make_response(df.to_csv(index=False))
        response.headers["Content-Disposition"] = "attachment; filename=user_data_filtered.csv"
        response.headers["Content-Type"] = "text/csv"
        return response
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect(url_for('dashboard'))

@app.route('/download/excel', methods=['POST'])
def download_excel():
    try:
        data = request.json
        if not data or 'details' not in data:
            flash('No data available', 'error')
            return redirect(url_for('dashboard'))

        details = data['details']
        filtered_details = [(detail['nic'], detail['dob'], detail['gender'], detail['age']) for detail in details]
        df = pd.DataFrame(filtered_details, columns=['NIC', 'Gender', 'DOB', 'Age'])

        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        df.to_excel(writer, index=False, sheet_name='UserData')
        writer._save()
        output.seek(0)

        response = make_response(output.read())
        response.headers["Content-Disposition"] = "attachment; filename=user_data_filtered.xlsx"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect(url_for('dashboard'))

@app.route('/download/pdf', methods=['POST'])
def download_pdf():
    try:
        data = request.json
        if not data or 'details' not in data:
            flash('No data available', 'error')
            return redirect(url_for('dashboard'))

        details = data['details']
        filtered_details = [(detail['nic'], detail['gender'], detail['dob'], detail['age']) for detail in details]

        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=letter)

        # Title
        title = Paragraph("<b>NIC Validator</b>", getSampleStyleSheet()["Title"])

        # Data for table
        table_data = [["NIC", "Gender", "DOB", "Age"]] + filtered_details

        # Create table
        table = Table(table_data, colWidths=[2 * inch, 1.5 * inch, 2 * inch, 1.5 * inch])

        # Table style
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#84df87")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ]))

        # Build PDF
        elements = [title, table]
        doc.build(elements)

        output.seek(0)

        response = make_response(output.read())
        response.headers["Content-Disposition"] = "attachment; filename=user_data_filtered.pdf"
        response.headers["Content-Type"] = "application/pdf"
        return response

    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect(url_for('dashboard'))

@app.route('/close_modal', methods=['POST'])
def close_modal():
    session['success_upload']=False
    return redirect(url_for('dashboard'))

@app.route('/test', methods=['GET', 'POST'])
def test():
    try:
        result = ['Male', '9/8/2009', 15]
        id = "392174724V"
        store_in_database(id, result)
        return render_template('dashboard.html')
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)