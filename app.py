import os
import re  # Şifre kriterlerini kontrol etmek için kullanılabilir
from datetime import datetime, timedelta
import sqlite3
from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash  # Bu satırın kesinlikle olması lazım

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_study_planner'

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

    # 1. Kullanıcının Özel Haftalık Hedefini Çekelim
    user_data = conn.execute('SELECT weekly_target FROM users WHERE id = ?', (user_id,)).fetchone()
    weekly_target = user_data['weekly_target'] if (user_data and user_data['weekly_target']) else 600

    # 2. Son 7 Günün Toplam Çalışma Süresi (Saniye olarak geliyor)
    weekly_query = conn.execute('''
        SELECT SUM(duration_seconds) 
        FROM study_sessions 
        WHERE user_id = ? AND end_time >= DATE('now', '-7 days')
    ''', (user_id,)).fetchone()
    
    weekly_seconds = weekly_query[0] if weekly_query[0] is not None else 0
    weekly_mins = weekly_seconds // 60 # İlerleme çubuğu için dakikaya çevirdik
    progress_percent = min(int((weekly_mins / weekly_target) * 100), 100)

    # =========================================================================
    # [US-04] DÜZELTİLDİ: Mevcut Haftanın Başlangıcından İtibaren Toplam Süre
    # =========================================================================
    today = datetime.now()
    start_of_this_week = today - timedelta(days=today.weekday())
    start_of_this_week = start_of_this_week.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week_str = start_of_this_week.strftime('%Y-%m-%d %H:%M:%S')

    current_week_query = conn.execute('''
        SELECT SUM(duration_seconds) 
        FROM study_sessions 
        WHERE user_id = ? AND end_time >= ?
    ''', (user_id, start_of_week_str)).fetchone()

    total_seconds_this_week = current_week_query[0] if current_week_query[0] is not None else 0
    
    # Saniyeyi önce toplam dakikaya çeviriyoruz!
    total_mins_this_week = total_seconds_this_week // 60
    
    # Şimdi saat ve dakikayı doğru hesaplıyoruz
    this_week_hours = total_mins_this_week // 60
    this_week_minutes = total_mins_this_week % 60

    # [US-04] Ders Bazlı Dağılım Sorgusu
    course_breakdown = conn.execute('''
        SELECT course_name, SUM(duration_seconds) as total_mins
        FROM study_sessions
        WHERE user_id = ? AND end_time >= ?
        GROUP BY course_name
    ''', (user_id, start_of_week_str)).fetchall()
    # =========================================================================

    # 3. En Çok Çalışılan Ders
    top_course_query = conn.execute('''
        SELECT course_name, SUM(duration_seconds) as total_dur
        FROM study_sessions
        WHERE user_id = ?
        GROUP BY course_name
        ORDER BY total_dur DESC LIMIT 1
    ''', (user_id,)).fetchone()
    top_course = top_course_query['course_name'] if top_course_query else "None"

    # 4. Verimlilik Oranı
    total_sessions_query = conn.execute('SELECT COUNT(*) FROM study_sessions WHERE user_id = ?', (user_id,)).fetchone()
    total_sessions = total_sessions_query[0]
    
    if total_sessions > 0:
        productive_query = conn.execute("SELECT COUNT(*) FROM study_sessions WHERE user_id = ? AND how_it_went = 'Productive'", (user_id,)).fetchone()
        prod_rate = int((productive_query[0] / total_sessions) * 100)
    else:
        prod_rate = 0

    # 5. Aktif Seans Kontrolü
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
                           total_mins=weekly_mins, 
                           weekly_target=weekly_target,
                           progress_percent=progress_percent,
                           course_breakdown=course_breakdown,
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
    
    # ID'nin gerçekten dolu ve geçerli olduğundan emin olalım (Giriş temizleme)
    if not course_id or str(course_id).strip() == "":
        flash("Please select a valid course before starting!")
        return redirect(url_for('index'))

    start_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = get_db_connection()
    conn.execute('DELETE FROM active_sessions WHERE user_id = ?', (user_id,))
    conn.execute('''
        INSERT INTO active_sessions (user_id, course_id, start_time, study_mode, pomo_state)
        VALUES (?, ?, ?, ?, 'study')
    ''', (user_id, int(course_id), start_time_str, study_mode)) # integer dönüşümü garantiye alındı
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
        
        # Saniye bazlı hesaplama
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
    # Veri tabanından ilgili kursu silme kodun (Örn: SQLite / SQLAlchemy)
    # course = Course.query.get(course_id)
    # db.session.delete(course)
    # db.session.commit()
    
    flash("Course deleted successfully!", "info")
    return redirect(url_for('index')) # index fonksiyonunun ismine göre düzenle

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

# Ana çalıştırma bloğu her zaman en altta kalmalı
if __name__ == '__main__':
    app.run(debug=True)