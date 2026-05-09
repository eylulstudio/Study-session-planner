import sqlite3
from flask import Flask, render_template

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return "<h1>Study Session Planner is working.!</h1><p>Database connection is ready.</p>"

if __name__ == '__main__':
    app.run(debug=True)