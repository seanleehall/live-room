from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import uuid
import time
import os
import hashlib

app = Flask(__name__, static_folder='.')
CORS(app)

DB = '/tmp/rooms.db'

def hash_pw(pw):
    if not pw:
        return ''
    return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS hosts (
        code TEXT PRIMARY KEY,
        name TEXT,
        primary_color TEXT,
        logo TEXT,
        password TEXT DEFAULT '',
        created INTEGER
    )''')
    try:
        c.execute('ALTER TABLE hosts ADD COLUMN password TEXT DEFAULT ""')
    except sqlite3.OperationalError:
        pass
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

def ensure_host(code):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT code FROM hosts WHERE code=?', (code,))
    if not c.fetchone():
        c.execute('INSERT INTO hosts (code, name, primary_color, logo, password, created) VALUES (?, ?, ?, ?, ?, ?)',
                  (code, 'pollme.live', '#1e3a5f', '', '', int(time.time())))
        conn.commit()
    conn.close()

def check_password(code, password):
    ensure_host(code)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT password FROM hosts WHERE code=?', (code,))
    row = c.fetchone()
    conn.close()
    if not row:
        return True
    stored = row[0] or ''
    if not stored:
        return True
    return stored == hash_pw(password or '')

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/host/check/<code>', methods=['GET'])
def check_code(code):
    code = code.upper().strip()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT code FROM hosts WHERE code=?', (code,))
    taken = c.fetchone() is not None
    conn.close()
    return jsonify({'code': code, 'taken': taken})

@app.route('/api/host', methods=['POST'])
def create_or_get_host():
    data = request.json or {}
    code = (data.get('code') or str(uuid.uuid4())[:6].upper()).upper()
    password = data.get('password', '')
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT * FROM hosts WHERE code=?', (code,))
    row = c.fetchone()
    if not row:
        c.execute('INSERT INTO hosts (code, name, primary_color, logo, password, created) VALUES (?, ?, ?, ?, ?, ?)',
                  (code, data.get('name', 'pollme.live'), data.get('primary', '#1e3a5f'), data.get('logo', ''), hash_pw(password), int(time.time())))
        conn.commit()
    conn.close()
    return jsonify({'code': code})

@app.route('/api/host/<code>/secure', methods=['POST'])
def secure_host(code):
    data = request.json or {}
    new_code = (data.get('code') or code).upper().strip()
    password = data.get('password', '')
    if not new_code or len(new_code) < 3:
        return jsonify({'error': 'Code must be at least 3 characters'}), 400
    ensure_host(code)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if new_code != code:
        c.execute('SELECT code FROM hosts WHERE code=?', (new_code,))
        if c.fetchone():
            conn.close()
            return jsonify({'error': 'That code is already taken'}), 400
        c.execute('UPDATE hosts SET code=? WHERE code=?', (new_code, code))
        c.execute('UPDATE questions SET host_code=? WHERE host_code=?', (new_code, code))
        c.execute('UPDATE sessions SET host_code=? WHERE host_code=?', (new_code, code))
    c.execute('UPDATE hosts SET password=? WHERE code=?', (hash_pw(password), new_code))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'code': new_code})

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

@app.route('/api/host/<code>/auth', methods=['POST'])
def auth_host(code):
    data = request.json or {}
    if check_password(code, data.get('password', '')):
        return jsonify({'ok': True})
    return jsonify({'error': 'Wrong password'}), 401

@app.route('/api/host/<code>/branding', methods=['POST'])
def update_branding(code):
    data = request.json
    if not check_password(code, request.headers.get('X-Password', data.get('password', ''))):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE hosts SET name=?, primary_color=?, logo=? WHERE code=?',
              (data.get('name'), data.get('primary'), data.get('logo'), code))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/host/<code>/questions', methods=['GET', 'POST'])
def questions(code):
    ensure_host(code)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if request.method == 'POST':
        data = request.json or {}
        pw = request.headers.get('X-Password') or data.get('password', '')
        if not check_password(code, pw):
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 401
        if not data.get('text'):
            conn.close()
            return jsonify({'error': 'Question text required'}), 400
        c.execute('INSERT INTO questions (host_code, text, qtype, options) VALUES (?, ?, ?, ?)',
                  (code, data['text'], data.get('type', 'yesno'), data.get('options', '')))
        conn.commit()
        qid = c.lastrowid
        conn.close()
        return jsonify({'id': qid})
    else:
        archived = request.args.get('archived', '0')
        c.execute('SELECT id, text, qtype, options, used, archived FROM questions WHERE host_code=? AND archived=?', (code, int(archived)))
        rows = c.fetchall()
        conn.close()
        return jsonify([{'id': r[0], 'text': r[1], 'type': r[2], 'options': r[3], 'used': r[4], 'archived': r[5]} for r in rows])

@app.route('/api/host/<code>/questions/<int:qid>', methods=['PUT', 'DELETE'])
def manage_question(code, qid):
    pw = request.headers.get('X-Password') or (request.json or {}).get('password', '')
    if not check_password(code, pw):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if request.method == 'DELETE':
        c.execute('DELETE FROM questions WHERE id=? AND host_code=?', (qid, code))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    else:
        data = request.json or {}
        c.execute('UPDATE questions SET text=?, options=?, qtype=? WHERE id=? AND host_code=?',
                  (data.get('text'), data.get('options', ''), data.get('type', 'custom'), qid, code))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

@app.route('/api/host/<code>/alltime', methods=['GET'])
def alltime_results(code):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''SELECT q.id, q.text, q.qtype, q.options, a.choice, COUNT(*) as cnt
                 FROM questions q
                 LEFT JOIN sessions s ON s.question_id = q.id
                 LEFT JOIN answers a ON a.session_id = s.id
                 WHERE q.host_code=? AND q.archived=0
                 GROUP BY q.id, a.choice''', (code,))
    rows = c.fetchall()
    conn.close()
    by_q = {}
    for qid, text, qtype, options, choice, cnt in rows:
        if qid not in by_q:
            by_q[qid] = {'id': qid, 'text': text, 'type': qtype, 'options': options, 'results': {}}
        if choice:
            by_q[qid]['results'][choice] = cnt
    return jsonify(list(by_q.values()))

@app.route('/api/host/<code>/questions/<int:qid>/archive', methods=['POST'])
def archive_question(code, qid):
    data = request.json or {}
    pw = request.headers.get('X-Password') or data.get('password', '')
    if not check_password(code, pw):
        return jsonify({'error': 'Unauthorized'}), 401
    archived = 1 if data.get('archived', True) else 0
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE questions SET archived=? WHERE id=? AND host_code=?', (archived, qid, code))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/session', methods=['POST'])
def start_session():
    data = request.json
    pw = request.headers.get('X-Password') or data.get('password', '')
    if not check_password(data['host'], pw):
        return jsonify({'error': 'Unauthorized'}), 401
    sid = str(uuid.uuid4())[:8]
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE sessions SET active=0 WHERE host_code=?', (data['host'],))
    c.execute('INSERT INTO sessions (id, host_code, question_id, started, duration) VALUES (?, ?, ?, ?, ?)',
              (sid, data['host'], data['question_id'], int(time.time()), data.get('duration', 0)))
    c.execute('UPDATE questions SET used = used + 1 WHERE id=?', (data['question_id'],))
    conn.commit()
    conn.close()
    return jsonify({'session_id': sid})

@app.route('/api/session/end', methods=['POST'])
def end_session():
    data = request.json
    pw = request.headers.get('X-Password') or data.get('password', '')
    if not check_password(data['host'], pw):
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE sessions SET active=0 WHERE host_code=?', (data['host'],))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/host/<code>/current', methods=['GET'])
def current_session(code):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''SELECT s.id, s.started, s.duration, s.active, q.text, q.qtype, q.options
                 FROM sessions s JOIN questions q ON s.question_id = q.id
                 WHERE s.host_code=? ORDER BY s.started DESC LIMIT 1''', (code,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'active': False})
    c.execute('SELECT choice, COUNT(*) FROM answers WHERE session_id=? GROUP BY choice', (row[0],))
    counts = dict(c.fetchall())
    conn.close()
    return jsonify({
        'active': bool(row[3]),
        'session_id': row[0],
        'started': row[1],
        'duration': row[2],
        'question': row[4],
        'type': row[5],
        'options': row[6],
        'results': counts
    })

@app.route('/api/answer', methods=['POST'])
def submit_answer():
    data = request.json
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT active FROM sessions WHERE id=?', (data['session_id'],))
    row = c.fetchone()
    if not row or not row[0]:
        conn.close()
        return jsonify({'error': 'not active'}), 400
    c.execute('INSERT INTO answers (session_id, choice, timestamp) VALUES (?, ?, ?)',
              (data['session_id'], data['choice'], int(time.time())))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
