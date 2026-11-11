from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import uuid
import time
import os

app = Flask(__name__, static_folder='.')
CORS(app)

DB = '/tmp/rooms.db'

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS hosts (
        code TEXT PRIMARY KEY,
        name TEXT,
        primary_color TEXT,
        logo TEXT,
        created INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        host_code TEXT,
        text TEXT,
        qtype TEXT,
        options TEXT,
        used INTEGER DEFAULT 0,
        archived INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        host_code TEXT,
        question_id INTEGER,
        started INTEGER,
        duration INTEGER,
        active INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        choice TEXT,
        timestamp INTEGER
    )''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/host', methods=['POST'])
def create_or_get_host():
    data = request.json or {}
    code = data.get('code') or str(uuid.uuid4())[:6].upper()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT * FROM hosts WHERE code=?', (code,))
    row = c.fetchone()
    if not row:
        c.execute('INSERT INTO hosts (code, name, primary_color, logo, created) VALUES (?, ?, ?, ?, ?)',
                  (code, data.get('name', 'Live Room'), data.get('primary', '#1e40af'), data.get('logo', ''), int(time.time())))
        conn.commit()
    conn.close()
    return jsonify({'code': code})

@app.route('/api/host/<code>', methods=['GET'])
def get_host(code):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT name, primary_color, logo FROM hosts WHERE code=?', (code,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'name': row[0], 'primary': row[1], 'logo': row[2]})

@app.route('/api/host/<code>/branding', methods=['POST'])
def update_branding(code):
    data = request.json
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE hosts SET name=?, primary_color=?, logo=? WHERE code=?',
              (data.get('name'), data.get('primary'), data.get('logo'), code))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/host/<code>/questions', methods=['GET', 'POST'])
def questions(code):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json
        c.execute('INSERT INTO questions (host_code, text, qtype, options) VALUES (?, ?, ?, ?)',
                  (code, data['text'], data.get('type', 'yesno'), data.get('options', '')))
        conn.commit()
        qid = c.lastrowid
        conn.close()
        return jsonify({'id': qid})
    else:
        c.execute('SELECT id, text, qtype, options, used FROM questions WHERE host_code=? AND archived=0', (code,))
        rows = c.fetchall()
        conn.close()
        return jsonify([{'id': r[0], 'text': r[1], 'type': r[2], 'options': r[3], 'used': r[4]} for r in rows])

@app.route('/api/session', methods=['POST'])
def start_session():
    data = request.json
    sid = str(uuid.uuid4())[:8]
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('INSERT INTO sessions (id, host_code, question_id, started, duration) VALUES (?, ?, ?, ?, ?)',
              (sid, data['host'], data['question_id'], int(time.time()), data.get('duration', 180)))
    c.execute('UPDATE questions SET used = used + 1 WHERE id=?', (data['question_id'],))
    conn.commit()
    conn.close()
    return jsonify({'session_id': sid})

@app.route('/api/session/<sid>', methods=['GET'])
def get_session(sid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''SELECT s.started, s.duration, s.active, q.text, q.qtype, q.options
                 FROM sessions s JOIN questions q ON s.question_id = q.id WHERE s.id=?''', (sid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    c.execute('SELECT choice, COUNT(*) FROM answers WHERE session_id=? GROUP BY choice', (sid,))
    counts = dict(c.fetchall())
    conn.close()
    return jsonify({
        'started': row[0],
        'duration': row[1],
        'active': row[2],
        'question': row[3],
        'type': row[4],
        'options': row[5],
        'results': counts
    })

@app.route('/api/answer', methods=['POST'])
def submit_answer():
    data = request.json
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('INSERT INTO answers (session_id, choice, timestamp) VALUES (?, ?, ?)',
              (data['session_id'], data['choice'], int(time.time())))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
