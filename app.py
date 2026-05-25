from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_study_planner'

import os

def get_db_connection():
    db_exists = os.path.exists('database.db')
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    
    # Eğer veritabanı dosyası yoksa schema.sql dosyasını okuyup sıfırdan tertemiz kurar
    if not db_exists:
        with open('schema.sql', 'r') as f:
            conn.executescript(f.read())
        conn.commit()
        print("🚀 Veritabanı ve tüm tablolar sıfırdan başarıyla kuruldu!")
        
    return conn

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()

    # 1. Kullanıcının Özel Haftalık Hedefini Çekelim (Yoksa varsayılan 600 dk)
    user_data = conn.execute('SELECT weekly_target FROM users WHERE id = ?', (user_id,)).fetchone()
    weekly_target = user_data['weekly_target'] if (user_data and user_data['weekly_target']) else 600

    # 2. Son 7 Günün Toplam Çalışma Süresi (Haftalık İlerleme)
    weekly_query = conn.execute('''
        SELECT SUM(duration_minutes) 
        FROM study_sessions 
        WHERE user_id = ? AND end_time >= DATE('now', '-7 days')
    ''', (user_id,)).fetchone()
    
    weekly_mins = weekly_query[0] if weekly_query[0] is not None else 0
    
    # İlerleme yüzdesi hesabı (%100'ü aşmasın)
    progress_percent = min(int((weekly_mins / weekly_target) * 100), 100)

    # 3. En Çok Çalışılan Ders (Top Focus Course)
    top_course_query = conn.execute('''
        SELECT course_name, SUM(duration_minutes) as total_dur
        FROM study_sessions
        WHERE user_id = ?
        GROUP BY course_name
        ORDER BY total_dur DESC LIMIT 1
    ''', (user_id,)).fetchone()
    top_course = top_course_query['course_name'] if top_course_query else "None"

    # 4. Verimlilik Oranı (Productivity Rate)
    total_sessions_query = conn.execute('SELECT COUNT(*) FROM study_sessions WHERE user_id = ?', (user_id,)).fetchone()
    total_sessions = total_sessions_query[0]
    
    if total_sessions > 0:
        productive_query = conn.execute("SELECT COUNT(*) FROM study_sessions WHERE user_id = ? AND how_it_went = 'Productive'", (user_id,)).fetchone()
        prod_rate = int((productive_query[0] / total_sessions) * 100)
    else:
        prod_rate = 0

    # 5. Aktif Seans Kontrolü (Kronometre Durumu)
    active_session = conn.execute('SELECT * FROM active_sessions WHERE user_id = ?', (user_id,)).fetchone()
    
    time_left = 0
    pomo_mode = 'regular'
    pomo_state = 'study'
    active_course = ""

    if active_session:
        pomo_mode = active_session['study_mode']
        pomo_state = active_session['pomo_state']
        course_id = active_session['course_id']
        
        c_data = conn.execute('SELECT course_name FROM courses WHERE id = ?', (course_id,)).fetchone()
        active_course = c_data['course_name'] if c_data else "Unknown"

        start_time_dt = datetime.strptime(active_session['start_time'], '%Y-%m-%d %H:%M:%S')
        elapsed = int((datetime.now() - start_time_dt).total_seconds())

        if pomo_mode == 'pomodoro':
            target_limit = 25 * 60 if pomo_state == 'study' else 5 * 60
            time_left = target_limit - elapsed
            if time_left < 0:
                time_left = 0
        else:
            time_left = elapsed

    courses = conn.execute('SELECT * FROM courses WHERE user_id = ?', (user_id,)).fetchall()
    
    # Ana sayfadaki Quick History tablosu için son 5 seansı çekelim
    latest_sessions = conn.execute('''
        SELECT course_name, duration_minutes, how_it_went, end_time 
        FROM study_sessions 
        WHERE user_id = ? 
        ORDER BY end_time DESC LIMIT 5
    ''', (user_id,)).fetchall()

    conn.close()

    return render_template('index.html', 
                           courses=courses, 
                           total_mins=weekly_mins, 
                           weekly_target=weekly_target,
                           progress_percent=progress_percent,
                           top_course=top_course, 
                           prod_rate=prod_rate,
                           active_session=active_session,
                           time_left=time_left,
                           pomo_mode=pomo_mode,
                           pomo_state=pomo_state,
                           active_course=active_course,
                           latest_sessions=latest_sessions)

@app.route('/update_target', methods=['POST'])
def update_target():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    new_target = request.form.get('weekly_target', type=int)
    
    if new_target and new_target > 0:
        conn = get_db_connection()
        conn.execute('UPDATE users SET weekly_target = ? WHERE id = ?', (new_target, user_id))
        conn.commit()
        conn.close()
        
    return redirect(url_for('index'))

@app.route('/start', methods=['POST'])
def start_session():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    course_id = request.form.get('course_id')
    study_mode = request.form.get('study_mode', 'regular')
    
    if not course_id:
        return redirect(url_for('index'))

    start_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = get_db_connection()
    conn.execute('DELETE FROM active_sessions WHERE user_id = ?', (user_id,))
    conn.execute('''
        INSERT INTO active_sessions (user_id, course_id, start_time, study_mode, pomo_state)
        VALUES (?, ?, ?, ?, 'study')
    ''', (user_id, course_id, start_time_str, study_mode))
    conn.commit()
    conn.close()
    
    return redirect(url_for('index'))

@app.route('/end', methods=['POST'])
def end_session():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    elapsed_seconds = request.form.get('elapsed_seconds', type=int, default=0)
    how_it_went = request.form.get('how_it_went', 'Neutral')
    notes = request.form.get('notes', '')

    conn = get_db_connection()
    active = conn.execute('SELECT * FROM active_sessions WHERE user_id = ?', (user_id,)).fetchone()
    
    if active:
        course_id = active['course_id']
        c_data = conn.execute('SELECT course_name FROM courses WHERE id = ?', (course_id,)).fetchone()
        course_name = c_data['course_name'] if c_data else "Unknown Subject"
        
        end_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn.execute('''
            INSERT INTO study_sessions (user_id, course_name, duration_minutes, how_it_went, notes, end_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, course_name, elapsed_seconds, how_it_went, notes, end_time_str))
        
        conn.execute('DELETE FROM active_sessions WHERE user_id = ?', (user_id,))
        conn.commit()
        
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_course', methods=['POST'])
def add_course():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    course_name = request.form.get('course_name')
    
    if course_name:
        conn = get_db_connection()
        conn.execute('INSERT INTO courses (user_id, course_name) VALUES (?, ?)', (user_id, course_name))
        conn.commit()
        conn.close()
        
    return redirect(url_for('index'))

@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    
    courses = conn.execute('SELECT * FROM courses WHERE user_id = ?', (user_id,)).fetchall()
    
    # Filtre Parametreleri
    course_filter = request.args.get('course', '')
    prod_filter = request.args.get('productivity', '')
    date_filter = request.args.get('specific_date', '')
    
    query = "SELECT * FROM study_sessions WHERE user_id = ?"
    params = [user_id]
    
    if course_filter:
        query += " AND course_name = ?"
        params.append(course_filter)
    if prod_filter:
        query += " AND how_it_went = ?"
        params.append(prod_filter)
    if date_filter:
        query += " AND DATE(end_time) = ?"
        params.append(date_filter)
        
    query += " ORDER BY end_time DESC"
    sessions = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    
    return render_template('history.html', sessions=sessions, courses=courses)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            conn.close()
            return redirect(url_for('index'))
        else:
            conn.execute('INSERT INTO users (username) VALUES (?)', (username,))
            conn.commit()
            new_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            session['user_id'] = new_user['id']
            session['username'] = new_user['username']
            conn.close()
            return redirect(url_for('index'))
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)