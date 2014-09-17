#!/usr/bin/env python -B

import os
import re

# Flask WSGI app
# ---------------------------
import flask
from flask import Flask, request, flash, url_for, redirect, Response, abort, g
app = Flask(__name__, static_folder='public')
app.secret_key = 'OyJbZXOkKDAXul52zZUtoQIT7SZM0VEFc9BuudzZhoA'

# GZip Responses
# ---------------------------
from flask.ext.compress import Compress
Compress(app)

# Conditional HTTP requests
# ---------------------------
from datetime import datetime
from werkzeug.http import is_resource_modified
launch_date = datetime.now()
@app.after_request
def handle_cache(response):
    """On 302 redirect, set no-cache headers. If resource is the same, return 304."""
    if response.status_code == 302:
        response.headers['Last-Modified'] = datetime.now()
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response

    elif response.status_code != 200:
        return response

    # If we set max-age=0, then make sure the response is not locally cached
    if response.cache_control.max_age == 0:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'

    matched = not is_resource_modified(request.environ, etag=response.headers.get('etag'))
    unmodified = not is_resource_modified(request.environ, last_modified=response.headers.get('last-modified'))
    return_304 = matched or unmodified
    return return_304 and Response(status=304) or response

# Auth
# ---------------------------
from flask.ext.login import login_user, logout_user, current_user, login_required
from flask.ext.login import LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

@app.before_request
def before_request():
    g.user = current_user
 
@app.route('/login.html', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        return flask.send_file('public/login.html', add_etags=False, conditional=False, cache_timeout=0)

    username = request.form['username']
    password = request.form['password']
    remember_me = ('remember_me' in request.form)

    registered_user = User.query.filter_by(username=username, password=password).first()
    if registered_user is None:
        flash('Username or password is invalid' , 'error')
        return redirect(url_for('login'))

    login_user(registered_user, remember=remember_me)
    return redirect(request.args.get('next') or url_for('index'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login')) 

# Storage
# ---------------------------
import json
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import UserMixin
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///tutorme.db')
db = SQLAlchemy(app)

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column('user_id', db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, index=True)
    password = db.Column(db.String(20))
    email = db.Column(db.String(50), index=True)
    registered_on = db.Column('registered_on' , db.DateTime)
    settings = db.relationship('Settings', uselist=False, backref='user')
    def __init__(self, username, password, email=''):
        self.username = username
        self.password = password
        self.email = email
        self.registered_on = datetime.utcnow()
    def __repr__(self):         return '<User %r>' % (self.username)

class Settings(db.Model):
    __tablename__ = "settings"
    id = db.Column('settings_id', db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    mastery = db.Column(db.Text())
    notes = db.Column(db.Text())
    hilites = db.Column(db.Text())
    testlist = db.Column(db.Text())

def get_settings():
    if g.user is None or g.user.is_anonymous() or g.user.settings is None: 
        abort(404)
    return g.user.settings

@app.route('/storage.js', methods=['HEAD', 'GET'])
def storage_script():
    response = storage()
    script = 'STORAGE_CACHE = %s;' % response.get_data().decode('utf-8')
    response.set_data(script)
    response.content_type = 'application/javascript; charset=utf-8'
    return response

@app.route('/storage', methods=['HEAD', 'GET'])
def storage():
    s = get_settings()
    return Response(
        '{"mastery" : %s, "notes": %s, "hilites": %s, "testlist": %s}\n' % 
            (s.mastery or 'null', s.notes or 'null', s.hilites or 'null', s.testlist or 'null'),
        content_type='application/json; charset=utf-8')

@app.route('/storage/<string:user>/<string:key>', methods=['PUT', 'POST', 'DELETE'])
def storage_by_key(user, key):
    settings = get_settings()
    if key not in settings.__dict__: abort(404)

    if request.method == 'DELETE':
        setattr(settings, key, '')
    else:
        data = request.get_data() or b''
        setattr(settings, key, data.decode(encoding='UTF-8'))

    db.session.commit()
    return Response(status=204)

@app.route('/storage/<string:user>/<string:key>/<string:index>', methods=['PUT', 'POST', 'DELETE'])
@login_required
def storage_by_key_and_index(user, key, index):
    '''Get the column "key" for the given user, which is a JSON object, and update its "index" field.'''
    settings = get_settings()
    if key not in settings.__dict__: abort(404)

    # Value in column 'key' is a json object
    obj = getattr(settings, key) or '{}'
    obj = json.loads(obj)

    # Update value and update DB
    if request.method == 'DELETE':
        if index in obj:
            del obj[index]
    else:
        data = request.get_data() or b''
        obj[index] = json.loads(data.decode(encoding='UTF-8'))

    setattr(settings, key, json.dumps(obj))
    db.session.commit()

    return Response(status=204)


# Static files
# ---------------------------
@app.route('/', methods=['HEAD', 'GET'])
@login_required
def index():
    return static_file('index.html')

@app.route('/<path:path>', methods=['HEAD', 'GET'])
def static_file(path):
    # Security check
    if '..' in path or path.startswith('/'): abort(404)

    # Auth or public file check
    if not g.user.is_authenticated() and not re.match('^static/(?:img|css|thirdparty)', path):
        return redirect(url_for('login', next='/%s?%s' % (path, request.query_string.decode('utf-8'))))

    # let send_static_file guess the correct MIME type
    return flask.send_file(os.path.join('public', path), conditional=True)

# Debug mode
# ---------------------------
if __name__ == '__main__':
    print('Running in debugging mode. Start normal server with: foreman start')
    app.debug = True
    app.run()
