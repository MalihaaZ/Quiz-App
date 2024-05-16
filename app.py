import re
from flask import Flask, render_template, request, redirect, url_for, flash, session
import json
import random
import pymysql
from datetime import datetime
import uuid
import hashlib

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configure the MySQL database connection
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'Maliha'
app.config['MYSQL_PASSWORD'] = '191410zz'
app.config['MYSQL_DB'] = 'quiz_app'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# Create a MySQL database connection
mysql = pymysql.connect(
    host=app.config['MYSQL_HOST'],
    user=app.config['MYSQL_USER'],
    password=app.config['MYSQL_PASSWORD'],
    db=app.config['MYSQL_DB'],
    cursorclass=pymysql.cursors.DictCursor
)

# Load questions from JSON file
with open('questions_template.json', 'r') as file:
    questions = json.load(file)

def select_random_questions(questions_list):
    with open('quiz_parameters.json', 'r') as params_file:
        params = json.load(params_file)
        num_questions = params.get('num_questions', 2)
    return random.sample(questions_list, num_questions)

def generate_session_id():
    return str(uuid.uuid4())

@app.route('/')
def homepage():
    return render_template('homepage.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form and 'email' in request.form:
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        cursor = mysql.cursor(pymysql.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        account = cursor.fetchone()
        if account:
            msg = 'Account already exists!'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            msg = 'Invalid email address!'
        elif not re.match(r'[A-Za-z0-9]+', username):
            msg = 'Username must contain only characters and numbers!'
        elif not username or not password or not email:
            msg = 'Please fill out the form!'
        else:
            cursor.execute('INSERT INTO users VALUES (NULL, %s, %s, %s)', (username, hashlib.sha256(password.encode()).hexdigest(), email))
            mysql.commit()
            flash('Signup Successful! Please log in.', 'success')
            return redirect(url_for('login'))
        cursor.close()
    elif request.method == 'POST':
        msg = 'Please fill out the form!'
    return render_template('signup.html', msg=msg)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        with mysql.cursor() as cursor:
            cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, hashed_password))
            user = cursor.fetchone()
        if user:
            session['user_id'] = user['id']
            flash('Login successful!', 'success')
            return redirect(url_for('display_exercise'))
        else:
            flash('Login Failed. Please check your login details and try again.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/exercise')
def display_exercise():
    if 'user_id' not in session:
        flash('Please log in to take the quiz.', 'warning')
        return redirect(url_for('login'))

    selected_questions = select_random_questions(questions)
    session['current_questions'] = selected_questions
    session['session_id'] = generate_session_id()
    session['page_load_time'] = datetime.now()
    with open('quiz_parameters.json', 'r') as params_file:
        params = json.load(params_file)
        num_questions = params.get('num_questions', 2)
        quiz_title = params.get('quiz_title', 'Quiz')
    return render_template('index.html', questions=selected_questions, num_questions=num_questions, quiz_title=quiz_title)

@app.route('/submit', methods=['POST'])
def submit():
    with open('quiz_parameters.json', 'r') as params_file:
        params = json.load(params_file)
        passing_level = params.get('passing_level', 0.9)
        num_questions = params.get('num_questions', 4)
    
    score = 0
    results = []
    selected_questions = session.get('current_questions', [])
    question_number = 1

    cursor = mysql.cursor()
    cursor.execute(
        "INSERT INTO session_info (session_id, page_load_time, submission_time, num_questions, passing_level) VALUES (%s, %s, %s, %s, %s)",
        (session.get('session_id'), session.get('page_load_time'), datetime.now(), num_questions, passing_level)
    )

    for question in selected_questions:
        user_answers = request.form.getlist(question['question'])
        correct_answers = question['correct_answers']

        is_correct = set(user_answers) == set(correct_answers) and len(user_answers) == len(correct_answers)

        if request.form.get("first_modified_" + str(question['question_id'])) == '':
            first_modified_time = None
        else:
            first_modified_time = request.form.get("first_modified_" + str(question['question_id']))

        if request.form.get("last_modified_" + str(question['question_id'])) == '':
            last_modified_time = None
        else:
            last_modified_time = request.form.get("last_modified_" + str(question['question_id']))

        query = '''INSERT INTO quiz_log (session_id, question_number, question_id, question, user_answers, correct_answers, is_correct, first_modified_time, last_modified_time) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)'''
        cursor.execute(query, (session.get('session_id'), question_number, question['question_id'], question['question'], '|'.join(user_answers), '|'.join(correct_answers), is_correct, first_modified_time, last_modified_time))

        results.append({
            'question_id': question['question_id'],
            'question': question['question'],
            'user_answers': user_answers,
            'correct_answers': correct_answers,
            'is_correct': is_correct,
        })

        if is_correct:
            score += 1

        question_number += 1

    mysql.commit()
    cursor.close()

    if 'user_id' in session:
        with mysql.cursor() as cursor:
            now = datetime.now()
            cursor.execute('INSERT INTO user_scores (user_id, score, timestamp) VALUES (%s, %s, %s)', (session['user_id'], score, now))
            mysql.commit()

    return render_template('result.html', score=score, total=len(selected_questions), results=results, passing_level=passing_level, selected_questions=selected_questions)

@app.route('/points')
def points():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    with mysql.cursor() as cursor:
        cursor.execute('''
            SELECT user_scores.score, user_scores.timestamp, users.username
            FROM user_scores
            JOIN users ON user_scores.user_id = users.id
            WHERE user_scores.user_id = %s
            ORDER BY user_scores.timestamp DESC
        ''', (session['user_id'],))
        scores = cursor.fetchall()
    return render_template('points.html', scores=scores)

@app.route('/browse')
def browse():
    print("Browse route is being accessed.")
    return render_template('empty.html')

# Community Page
@app.route('/community', methods=['GET', 'POST'])
def community():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        user_id = session['user_id']
        cursor = mysql.cursor()
        cursor.execute('INSERT INTO posts (user_id, title, content) VALUES (%s, %s, %s)', (user_id, title, content))
        mysql.commit()
        cursor.close()
        return redirect(url_for('community'))  # Redirect after POST

    with mysql.cursor() as cursor:
        cursor.execute('SELECT posts.id, posts.title, posts.content, posts.timestamp, users.username FROM posts JOIN users ON posts.user_id = users.id ORDER BY posts.timestamp DESC')
        posts = cursor.fetchall()
    return render_template('community.html', posts=posts)

@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def post(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        content = request.form['content']
        user_id = session['user_id']
        cursor = mysql.cursor()
        cursor.execute('INSERT INTO comments (post_id, user_id, content) VALUES (%s, %s, %s)', (post_id, user_id, content))
        mysql.commit()
        cursor.close()
        return redirect(url_for('post', post_id=post_id))  # Redirect after POST

    with mysql.cursor() as cursor:
        cursor.execute('SELECT posts.id, posts.title, posts.content, posts.timestamp, users.username FROM posts JOIN users ON posts.user_id = users.id WHERE posts.id = %s', (post_id,))
        post = cursor.fetchone()
        cursor.execute('SELECT comments.content, comments.timestamp, users.username FROM comments JOIN users ON comments.user_id = users.id WHERE comments.post_id = %s ORDER BY comments.timestamp DESC', (post_id,))
        comments = cursor.fetchall()
    return render_template('post.html', post=post, comments=comments)

if __name__ == '__main__':
    app.run(debug=True)
