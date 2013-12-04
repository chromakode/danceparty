import binascii
import cStringIO
import hashlib
import logging
import os
import random
import time
import uuid
from functools import wraps

import bcrypt
import couchdb
from PIL import Image
from flask import (
    g,
    json,
    abort,
    redirect,
    request,
    Response,
    render_template,
    session,
    send_from_directory,
    url_for,
)
from werkzeug.security import safe_str_cmp

from danceparty import app


if not app.debug:
    file_handler = logging.FileHandler(app.config['LOG_FILE'])
    file_handler.setLevel(logging.WARNING)
    app.logger.addHandler(file_handler)


def check_gif(data):
    img_stream = cStringIO.StringIO(data)
    try:
        img = Image.open(img_stream)
        return img.format == 'GIF'
    except IOError:
        return False


def connect_db():
    g.couch = couchdb.client.Server()
    db_name = app.config['DB_NAME']
    if not db_name in g.couch:
        g.couch.create(db_name)
    g.db = g.couch[db_name]

    views = {
        '_id': '_design/' + db_name,
        'language': 'javascript',
        'views': {
            'approved': {
                'map': "function(doc) { if (doc.status == 'approved') { emit(doc.ts, doc) } }"
            },
            'review-queue': {
                'map': "function(doc) { if (doc.status == 'new') { emit(doc.ts, doc) } }"
            },
            'all': {
                'map': "function(doc) {  emit(doc.ts, doc) }"
            },
        },
    }
    doc = g.db.get(views['_id'], {})
    if doc.get('views') != views['views']:
        doc.update(views)
        g.db.save(doc)


def dance_json(dance):
    data = {}
    data['id'] = dance['_id']
    data['ts'] = dance['ts']
    data['url'] = '/dance/'  + dance['_id'] + '.gif'
    if g.is_reviewer:
        data['status'] = dance['status']
    return data


def dances_json(view, limit=100, shuffle=False):
    rows = g.db.view(view, limit=limit, include_docs=True)
    if shuffle:
        rows = random.sample(rows, min(limit, len(rows)))
    return [dance_json(row.doc) for row in rows]


def require_reviewer(f):
    @wraps(f)
    def with_auth(*args, **kwargs):
        if request.scheme != 'https':
            return redirect(url_for(
                request.endpoint,
                _scheme='https',
                _external='true'
            ))

        if not g.is_reviewer:
            return Response(
                'Could not verify your access level for that URL.\n'
                'You have to login with proper credentials', 401,
                {'WWW-Authenticate': 'Basic realm="mc"'})
        else:
            return f(*args, **kwargs)

    return with_auth


def csrf_token(salt=None):
    if not session.get('csrft'):
        session['csrft'] = binascii.b2a_hex(os.urandom(16))
    return session['csrft']


@app.before_request
def before_request():
    g.couch = connect_db()

    if request.method not in ['GET', 'HEAD', 'OPTIONS']:
        if (not request.headers.get('X-CSRFT') or
                not session.get('csrft') or
                not safe_str_cmp(session['csrft'], request.headers['X-CSRFT'])):
            abort(400)

    g.is_reviewer = False
    auth = request.authorization
    if (auth and request.scheme == 'https' and
        safe_str_cmp(auth.username, app.config['REVIEWER_USERNAME'])):
        crypted = bcrypt.hashpw(auth.password, app.config['REVIEWER_PASSWORD'])
        if safe_str_cmp(crypted, app.config['REVIEWER_PASSWORD']):
            g.is_reviewer = True


@app.route('/')
def dances_plz():
    return render_template('dance.html',
        dances_json=dances_json('danceparty/approved'),
        config={'mode': 'party', 'csrft': csrf_token()},
    )


@app.route('/review')
@app.route('/review/all')
@require_reviewer
def review_dances_plz():
    if request.path.endswith('all'):
        query = 'danceparty/all'
    else:
        query = 'danceparty/review-queue'

    return render_template('dance.html',
        dances_json=dances_json(query),
        config={'mode': 'review', 'csrft': csrf_token()},
    )


@app.route('/dance/<dance_id>', methods=['GET'])
def get_dance(dance_id):
    dance = g.db[dance_id]
    return json.jsonify(dance_json(dance))


@app.route('/dance/<dance_id>', methods=['PUT'])
@require_reviewer
def update_dance(dance_id):
    dance = g.db[dance_id]
    data = request.get_json()
    if data['status'] in ['new', 'approved', 'rejected']:
        dance['status'] = data['status']
    g.db.save(dance)
    return json.jsonify(dance_json(dance))


@app.route('/dance', methods=['POST'])
def upload_dance():
    gif = request.files['moves']
    gif_data = gif.read()
    if gif and check_gif(gif_data):
        dance_id = hashlib.sha1(gif_data).hexdigest()
        dance = {
            '_id': dance_id,
            'ts': time.time(),
            'ip': request.remote_addr,
            'ua': request.user_agent.string,
            'status': 'new',
        }
        g.db.save(dance)
        with open(os.path.join(app.config['UPLOAD_FOLDER'], dance_id + '.gif'), 'w') as out:
            out.write(gif_data)
        return get_dance(dance_id)


@app.route('/dance/<dance_id>.gif')
def uploaded_file(dance_id):
    if app.debug:
        return send_from_directory(app.config['UPLOAD_FOLDER'], dance_id + '.gif')
