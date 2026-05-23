from flask import Flask, render_template, request, redirect, url_for, session, g, flash
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_study_planner'
DATABASE = 'database.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ---- DASHBOARD & TIMER ROTALARI ----

@app.route('/')
def index():
    if 'user_id' not in session:
        # Kolay test edebilmen için oturum yoksa otomatik giriş yapıyoruz
        session['user_id'] = 1
        session['username'] = 'student'
        
    user_id = session['user_id']
    db = get_db()
    
    # 🚨 KORUMA: Eğer database silindiyse veya dersler yoksa otomatik ekle
    check_courses = db.execute("SELECT COUNT(*) as count FROM courses WHERE user_id = ?", (user_id,)).fetchone()
    if check_courses['count'] == 0:
        db.execute("INSERT INTO courses (user_id, course_name) VALUES (?, 'Math')", (user_id,))
        db.execute("INSERT INTO courses (user_id, course_name) VALUES (?, 'Software')", (user_id,))
        db.execute("INSERT INTO courses (user_id, course_name) VALUES (?, 'Physics')", (user_id,))
        db.commit()
    
    courses = db.execute("SELECT * FROM courses WHERE user_id = ?", (user_id,)).fetchall()
    
    active_session = db.execute(
        "SELECT * FROM study_sessions WHERE user_id = ? AND end_time IS NULL", 
        (user_id,)
    ).fetchone()
    
    active_course = None
    pomo_mode = "regular"
    pomo_state = "study"
    time_left_seconds = 0

    if active_session:
        course_res = db.execute("SELECT course_name FROM courses WHERE id = ?", (active_session['course_id'],)).fetchone()
        if course_res:
            active_course = course_res['course_name']
        
        pomo_mode = active_session['pomo_mode']
        pomo_state = active_session['pomo_state']
        
        start_time = datetime.strptime(active_session['last_state_change'], '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        elapsed_seconds = int((now - start_time).total_seconds())

        if pomo_mode == 'pomodoro':
            target_duration = 25 * 60 if pomo_state == 'study' else 5 * 60
            
            # Python ile otomatik döngü geçiş kontrolü
            if elapsed_seconds >= target_duration:
                new_state = 'break' if pomo_state == 'study' else 'study'
                current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                if pomo_state == 'study':
                    db.execute("""
                        UPDATE study_sessions 
                        SET duration_minutes = duration_minutes + 25, pomo_state = ?, last_state_change = ?
                        WHERE id = ?
                    """, (new_state, current_time_str, active_session['id']))
                else:
                    db.execute("""
                        UPDATE study_sessions 
                        SET pomo_state = ?, last_state_change = ?
                        WHERE id = ?
                    """, (new_state, current_time_str, active_session['id']))
                db.commit()
                
                pomo_state = new_state
                elapsed_seconds = 0
                target_duration = 25 * 60 if pomo_state == 'study' else 5 * 60

            time_left_seconds = target_duration - elapsed_seconds
        else:
            time_left_seconds = elapsed_seconds + (active_session['duration_minutes'] * 60)

    # Haftalık İstatistik
    total_week_mins = 0
    stats_total = db.execute("SELECT SUM(duration_minutes) as total FROM study_sessions WHERE user_id = ? AND end_time IS NOT NULL", (user_id,)).fetchone()
    if stats_total and stats_total['total']:
        total_week_mins = stats_total['total']

    return render_template(
        'index.html', courses=courses, active_session=active_session, active_course=active_course,
        total_mins=total_week_mins, top_course="Software", prod_rate=100,
        pomo_mode=pomo_mode, pomo_state=pomo_state, time_left=time_left_seconds
    )

@app.route('/add_course', methods=['POST'])
def add_course():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    course_name = request.form.get('course_name').strip()
    user_id = session['user_id']
    
    if course_name:
        db = get_db()
        # Kullanıcının aynı isimde mükerrer ders eklemesini engellemek için saf SQL kontrolü
        existing = db.execute("SELECT id FROM courses WHERE user_id = ? AND course_name = ?", (user_id, course_name)).fetchone()
        
        if not existing:
            db.execute("INSERT INTO courses (user_id, course_name) VALUES (?, ?)", (user_id, course_name))
            db.commit()
            flash('Course added successfully!', 'success')
        else:
            flash('This course already exists!', 'warning')
            
    return redirect(url_for('index'))

@app.route('/start', methods=['POST'])
def start_session():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    course_id = request.form.get('course_id')
    study_mode = request.form.get('study_mode', 'regular')
    
    db = get_db()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    db.execute("""
        INSERT INTO study_sessions (user_id, course_id, start_time, duration_minutes, pomo_mode, pomo_state, last_state_change) 
        VALUES (?, ?, ?, 0, ?, 'study', ?)
    """, (user_id, course_id, current_time, study_mode, current_time))
    db.commit()
        
    return redirect(url_for('index'))

@app.route('/end', methods=['POST'])
def end_session():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    db = get_db()
    how_it_went = request.form.get('how_it_went')
    notes = request.form.get('notes')
    user_id = session['user_id']
    
    active_session = db.execute("SELECT * FROM study_sessions WHERE user_id = ? AND end_time IS NULL", (user_id,)).fetchone()
    
    if active_session:
        end_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        start_time = datetime.strptime(active_session['last_state_change'], '%Y-%m-%d %H:%M:%S')
        elapsed_mins = int((datetime.now() - start_time).total_seconds() / 60)
        
        final_duration = active_session['duration_minutes']
        if active_session['pomo_state'] == 'study':
            final_duration += elapsed_mins
        if final_duration < 1: final_duration = 1

        db.execute("""
            UPDATE study_sessions 
            SET end_time = ?, duration_minutes = ?, how_it_went = ?, notes = ? 
            WHERE id = ?
        """, (end_time_str, final_duration, how_it_went, notes, active_session['id']))
        db.commit()
            
    return redirect(url_for('history'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    session['user_id'] = 1
    session['username'] = 'student'
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Şemayı otomatik ayağa kaldırma mekanizması
    if not os.path.exists(DATABASE):
        conn = sqlite3.connect(DATABASE)
        with open('schema.sql', 'r') as f:
            conn.executescript(f.read())
        conn.close()
        print("🆕 Yeni temiz veritabanı kuruldu.")
        
    app.run(debug=True)

@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    db = get_db()
    sessions = db.execute('''
        SELECT course_name, duration_minutes, how_it_went, notes, end_time 
        FROM study_sessions 
        WHERE user_id = ? 
        ORDER BY end_time DESC
    ''', (session['user_id'],)).fetchall()
    
    return render_template('history.html', sessions=sessions)

# Veritabanı mesajı ve app.run her zaman EN ALTTA kalmalı:
print("🆕 Yeni temiz veritabanı kuruldu.")
app.run(debug=True)