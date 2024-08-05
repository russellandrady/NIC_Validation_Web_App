from flask import Flask, request, jsonify, render_template, make_response
from dotenv import load_dotenv
import os
import jwt
from flask_cors import CORS

load_dotenv()

app=Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.getenv('SECRET_KEY')

@app.route('/', methods=['GET','POST'])
def home():
    token = request.args.get('token')
    if token:
        try:
            decoded = jwt.decode(token, app.secret_key, algorithms=['HS256'])
            user_id = decoded['user_id']
            resp = make_response(render_template('index.html', id=user_id))
            resp.set_cookie('token', token, httponly=True, samesite='Strict')
            return resp
        except jwt.ExpiredSignatureError:
            print('Expired token')
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            print('Invalid token')
            return jsonify({'error': 'Invalid token'}), 401
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001)