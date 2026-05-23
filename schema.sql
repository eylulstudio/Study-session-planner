CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_name TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS study_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    duration_minutes INTEGER DEFAULT 0,
    how_it_went TEXT,
    notes TEXT,
    pomo_mode TEXT DEFAULT 'regular',       -- 'regular' veya 'pomodoro'
    pomo_state TEXT DEFAULT 'study',       -- 'study' veya 'break'
    last_state_change TEXT,                -- Durumun en son ne zaman değiştiği
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(course_id) REFERENCES courses(id)
);