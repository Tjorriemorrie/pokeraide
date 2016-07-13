from backend import app
from flask import render_template


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    return render_template('index.html')


# ev = our equity * total pot - cost of our call
