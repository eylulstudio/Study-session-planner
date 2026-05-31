import os
import re 
from datetime import datetime, timedelta
import sqlite3
from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash 

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_study_planner'

def get_db_connection():
    db_exists = os.path.exists('database.db')
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    
    if not db_exists:
        with open('schema.sql', 'r') as f:
            conn.executescript(f.read())
        conn.commit()
        print("🚀 Veritabanı ve tüm tablolar sıfırdan başarıyla kuruldu!")
        
    return conn

# =========================================================================
# BUSINESS LOGIC FUNCTIONS (UNIT TESTLER İÇİN ÖZEL OLARAK AYRILDI)
# =========================================================================

def calculate_weekly_stats(total_seconds_this_week, db_weekly_target_mins):
    """Haftalık toplam süreye göre saat, dakika ve ilerleme yüzdesini hesaplar."""
    total_mins_this_week = total_seconds_this_week // 60
    this_week_hours = total_mins_this_week // 60
    this_week_minutes = total_mins_this_week % 60

    if db_weekly_target_mins > 0:
        progress_percent = min(int((total_mins_this_week / db_weekly_target_mins) * 100), 100)
    else:
        progress_percent = 0
        
    return total_mins_this_week, this_week_hours, this_week_minutes, progress_percent

def generate_comparison_message(total_mins_this_week, total_mins_last_week):
    """Bu haftaki performansı geçen haftayla kıyaslayan metni üretir."""
    diff_mins = total_mins_this_week - total_mins_last_week
    abs_diff_mins = abs(diff_mins)
    diff_hours = abs_diff_mins // 60
    diff_remaining_mins = abs_diff_mins % 60

    time_str_list = []
    if diff_hours > 0:
        time_str_list.append(f"{diff_hours} hour{'s' if diff_hours > 1 else ''}")
    if diff_remaining_mins > 0 or diff_hours == 0:
        time_str_list.append(f"{diff_remaining_mins} minute{'s' if diff_remaining_mins > 1 else ''}")
    formatted_diff_time = " and ".join(time_str_list)

    if diff_mins > 0:
        return f"You studied {formatted_diff_time} more than last week! 🚀"
    elif diff_mins < 0:
        return f"You are {formatted_diff_time} behind last week's progress. Keep going! ⏱️"
    else:
        return "You have matched last week's study time exactly so far! 🎯"


# =========================================================================
# ROUTES (FLASK ENDPOINTS)
# =========================================================================

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()

    # 1. Kullanıcının Özel Haftalık Hedefini Çekelim
    user_data = conn.execute('SELECT weekly_target FROM users WHERE id = ?', (user_id,)).fetchone()
    db_weekly_target_mins = user_data['weekly_target'] if (user_data and user_data['weekly_target']) else 600
    weekly_target_hours = db_weekly_target_mins // 60

    # Zaman aralıklarının tanımlanması (Pazartesi 00:00:00)
    today = datetime.now()
    start_of_this_week = today - timedelta(days=today.weekday())
    start_of_this_week = start_of_this_week.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week_str = start_of_this_week.strftime('%Y-%m-%d %H:%M:%S')

    start_of_last_week = start_of_this_week - timedelta(days=7)
    end_of_last_week = start_of_this_week - timedelta(seconds=1)
    start_of_last_week_str = start_of_last_week.strftime('%Y-%m-%d %H:%M:%S')
    end_of_last_week_str = end_of_last_week.strftime('%Y-%m-%d %H:%M:%S')

    # BU HAFTAKİ TOPLAM GENEL SÜRE SORGUSU
    current_week_query = conn.execute('''
        SELECT SUM(duration_seconds) 
        FROM study_sessions 
        WHERE user_id = ? AND end_time >= ?
    ''', (user_id, start_of_week_str)).fetchone()

    total_seconds_this_week = current_week_query[0] if current_week_query[0] is not None else 0
    
    # Business Logic fonksiyonumuzu çağırıyoruz
    total_mins_this_week, this_week_hours, this_week_minutes, progress_percent = calculate_weekly_stats(
        total_seconds_this_week, db_weekly_target_mins
    )

    # GEÇEN HAFTAKİ TOPLAM SÜRE SORGUSU
    last_week_query = conn.execute('''
        SELECT SUM(duration_seconds) 
        FROM study_sessions 
        WHERE user_id = ? AND end_time >= ? AND end_time <= ?
    ''', (user_id, start_of_last_week_str, end_of_last_week_str)).fetchone()

    total_seconds_last_week = last_week_query[0] if last_week_query[0] is not None else 0
    total_mins_last_week = total_seconds_last_week // 60

    # Geçen haftayla kıyaslama metnini üreten fonksiyonu çağırıyoruz
    comparison_message = generate_comparison_message(total_mins_this_week, total_mins_last_week)

    # DERS BAZLI DAĞILIM SORGUSU
    course_breakdown = conn.execute('''
        SELECT course_name, SUM(duration_seconds) as total_course_seconds
        FROM study_sessions
        WHERE user_id = ? AND end_time >= ?
        GROUP BY course_name
    ''', (user_id, start_of_week_str)).fetchall()
    
    breakdown_total_seconds = sum(row['total_course_seconds'] for row in course_breakdown if row['total_course_seconds'] is not None)

    course_breakdown_clean = []
    for row in course_breakdown:
        c_total_seconds = row['total_course_seconds'] if row['total_course_seconds'] is not None else 0
        c_total_mins = c_total_seconds // 60
        c_hours = c_total_mins // 60
        c_remaining_mins = c_total_mins % 60
        
        calc_denominator = breakdown_total_seconds if breakdown_total_seconds > 0 else total_seconds_this_week

        if calc_denominator > 0:
            c_percent = min(int((c_total_seconds / calc_denominator) * 100), 100)
            if c_percent == 0 and c_total_seconds > 0:
                c_percent = 8
        else:
            c_percent = 0
            
        course_breakdown_clean.append({
            'course_name': row['course_name'],
            'hours': c_hours,
            'minutes': c_remaining_mins,
            'percent': c_percent
        })

    # En Çok Çalışılan Ders
    top_course_query = conn.execute('''
        SELECT course_name, SUM(duration_seconds) as total_dur
        FROM study_sessions
        WHERE user_id = ?
        GROUP BY course_name
        ORDER BY total_dur DESC LIMIT 1
    ''', (user_id,)).fetchone()
    top_course = top_course_query['course_name'] if top_course_query else "None"

    # Verimlilik Oranı
    total_sessions_query = conn.execute('SELECT COUNT(*) FROM study_sessions WHERE user_id = ?', (user_id,)).fetchone()
    total_sessions = total_sessions_query[0]
    
    if total_sessions > 0:
        productive_query = conn.execute("SELECT COUNT(*) FROM study_sessions WHERE user_id = ? AND how_it_went = 'Productive'", (user_id,)).fetchone()
        prod_rate = int((productive_query[0] / total_sessions) * 100)
    else:
        prod_rate = 0

    # Aktif Seans Kontrolü
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
            if time_left < 0: time_left = 0
        else:
            time_left = elapsed

    courses = conn.execute('SELECT * FROM courses WHERE user_id = ?', (user_id,)).fetchall()
    latest_sessions = conn.execute('''
        SELECT course_name, duration_seconds, how_it_went, end_time 
        FROM study_sessions 
        WHERE user_id = ? 
        ORDER BY end_time DESC LIMIT 5
    ''', (user_id,)).fetchall()

    conn.close()

    return render_template('index.html', 
                           courses=courses, 
                           total_mins=total_mins_this_week,
                           weekly_target=weekly_target_hours,
                           progress_percent=progress_percent,
                           course_breakdown=course_breakdown_clean,
                           comparison_message=comparison_message, 
                           top_course=top_course, 
                           prod_rate=prod_rate,
                           active_session=active_session,
                           time_left=time_left,
                           pomo_mode=pomo_mode,
                           pomo_state=pomo_state,
                           active_course=active_course,
                           latest_sessions=latest_sessions,
                           this_week_hours=this_week_hours,
                           this_week_minutes=this_week_minutes)

@app.route('/update_target', methods=['POST'])
def update_target():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    new_target_hours = request.form.get('weekly_target', type=int)
    
    if new_target_hours and new_target_hours > 0:
        new_target_minutes = new_target_hours * 60
        
        conn = get_db_connection()
        conn.execute('UPDATE users SET weekly_target = ? WHERE id = ?', (new_target_minutes, user_id))
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
    
    if not course_id or str(course_id).strip() == "":
        flash("Please select a valid course before starting!")
        return redirect(url_for('index'))

    start_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = get_db_connection()
    conn.execute('DELETE FROM active_sessions WHERE user_id = ?', (user_id,))
    conn.execute('''
        INSERT INTO active_sessions (user_id, course_id, start_time, study_mode, pomo_state)
        VALUES (?, ?, ?, ?, 'study')
    ''', (user_id, int(course_id), start_time_str, study_mode))
    conn.commit()
    conn.close()
    
    return redirect(url_for('index'))

@app.route('/end', methods=['POST'])
def end_session():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    how_it_went = request.form.get('how_it_went', 'Neutral')
    notes = request.form.get('notes', '')

    conn = get_db_connection()
    active = conn.execute('SELECT * FROM active_sessions WHERE user_id = ?', (user_id,)).fetchone()
    
    if active:
        course_id = active['course_id']
        c_data = conn.execute('SELECT course_name FROM courses WHERE id = ?', (course_id,)).fetchone()
        course_name = c_data['course_name'] if c_data else "Unknown"
        
        start_time_dt = datetime.strptime(active['start_time'], '%Y-%m-%d %H:%M:%S')
        duration_seconds = int((datetime.now() - start_time_dt).total_seconds())

        conn.execute('''
            INSERT INTO study_sessions (user_id, course_name, duration_seconds, how_it_went, notes, end_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, course_name, duration_seconds, how_it_went, notes, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
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

@app.route('/delete_course/<int:course_id>', methods=['POST'])
def delete_course(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    conn = get_db_connection()
    
    # Güvenlik ve Tam CRUD kuralı için sadece bu kullanıcıya ait olan dersi siliyoruz
    conn.execute('DELETE FROM courses WHERE id = ? AND user_id = ?', (course_id, user_id))
    conn.commit()
    conn.close()
    
    flash("Course deleted successfully!", "info")
    return redirect(url_for('index'))

@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    
    courses = conn.execute('SELECT * FROM courses WHERE user_id = ?', (user_id,)).fetchall()
    
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

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        
        if not username or not password:
            flash('Username and password cannot be empty!')
            return redirect(url_for('register'))
            
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user:
            conn.close()
            flash('This username is already taken! Choose another one.')
            return redirect(url_for('register'))
            
        if len(password) < 6:
            conn.close()
            flash('Password must be at least 6 characters long!')
            return redirect(url_for('register'))
            
        if not any(char.isupper() for char in password):
            conn.close()
            flash('Password must contain at least one uppercase letter (A-Z)!')
            return redirect(url_for('register'))
            
        if not any(char.isdigit() for char in password):
            conn.close()
            flash('Password must contain at least one number (0-9)!')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        conn.commit()
        conn.close()
        
        flash('Registration successful! You can now log in.')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password!')
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)