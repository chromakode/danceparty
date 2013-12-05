import binascii
import cStringIO
import hashlib
import hmac
import logging
import os
import random
import time
import uuid
from threading import Thread
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


def poll_dances_cache():
    while True:
        time.sleep(app.config['CACHE_POLL_INTERVAL'])
        update_dances_cache()


dances_cache = None
def update_dances_cache():
    global dances_cache
    with app.test_request_context('/'):
        connect_db()
        g.is_reviewer = False
        dances_cache = dances_json('danceparty/approved')


@app.before_first_request
def setup_app():
    if not app.debug and app.config['LOG_FILE']:
        file_handler = logging.FileHandler(app.config['LOG_FILE'])
        file_handler.setLevel(logging.WARNING)
        app.logger.addHandler(file_handler)
    create_db()

    update_dances_cache()
    poller = Thread(target=poll_dances_cache)
    poller.daemon = True
    poller.start()


def create_db():
    couch = couchdb.client.Server()
    db_name = app.config['DB_NAME']
    if not db_name in couch:
        couch.create(db_name)
    db = couch[db_name]

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
            'upload_rate': {
                'map': "function(doc) { if(doc.status != 'approved') { emit(doc.ip, [doc.ts]) } }",
                'reduce': "function (key, values, rereduce) { return [].concat.apply([], values).sort().reverse().slice(0,%d); }"%(app.config['UPLOAD_RATE_COUNT']*2) #it is assumed if the majority of the uploads in the bucket are approved that they aren't spammers.
            },
        }
    }
    doc = db.get(views['_id'], {})
    if doc.get('views') != views['views']:
        doc.update(views)
        db.save(doc)


def connect_db():
    couch = couchdb.client.Server()
    g.db = couch[app.config['DB_NAME']]


def check_gif(data):
    img_stream = cStringIO.StringIO(data)

    try:
        img = Image.open(img_stream)
        if img.format != 'GIF':
            return False
    except IOError:
        return False

    # Loop through frames adding up delays until we run out of frames or exceed
    # 1 second.
    duration = img.info['duration']
    try:
        # Go through frames summing the durations until we run out of ms in the
        # second limit. (or, an extra frame)
        while duration <= 1000:
            img.seek(img.tell() + 1)
            duration += img.info['duration']

        # If we leave the while loop without an error, we exceeded the time bound.
        return False

    # We reached the last frame without exceeding the while loops ms time bound.
    except EOFError:
        return True


def dance_owner_token(dance_id):
    return hmac.new(app.config['SECRET_KEY'], 'owner:' + dance_id).hexdigest()


def dance_json(dance):
    data = {}
    data['id'] = dance['_id']
    data['ts'] = dance['ts']
    data['url'] = '/dance/' + dance['_id'] + '.gif'

    scheme = request.scheme.upper()
    if scheme in ('HTTP', 'HTTPS'):
        cdn_key = 'CDN_%s_HOST' % request.scheme.upper()
        if app.config[cdn_key]:
            data['url'] = '//' + app.config[cdn_key] + data['url']

    if g.is_reviewer:
        data['status'] = dance['status']
    return data


def dances_json(view, limit=100, shuffle=False):
    rows = g.db.view(view, descending=True, limit=limit, include_docs=True)
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
    connect_db()

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
        dances_json=dances_cache,
        config_data={'mode': 'party', 'csrft': csrf_token()},
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
        config_data={'mode': 'review', 'csrft': csrf_token()},
    )


@app.route('/dance/<dance_id>', methods=['GET'])
def get_dance(dance_id):
    dance = g.db.get(dance_id)
    if dance and (dance['status'] != 'removed' or g.is_reviewer):
        return json.jsonify(dance_json(dance))
    else:
        abort(404)


@app.route('/dance/<dance_id>', methods=['PUT'])
@require_reviewer
def update_dance(dance_id):
    dance = g.db[dance_id]
    data = request.get_json()
    if data['status'] in ['new', 'approved', 'rejected', 'removed']:
        dance['status'] = data['status']
    g.db.save(dance)
    return json.jsonify(dance_json(dance))


@app.route('/dance/<dance_id>', methods=['DELETE'])
def remove_dance(dance_id):
    token = request.headers.get('X-Owner-Token')
    if not token or not safe_str_cmp(token, dance_owner_token(dance_id)):
        abort(403)
    dance = g.db[dance_id]
    dance['status'] = 'removed'
    g.db.save(dance)
    return '', 200


@app.route('/dance', methods=['POST'])
def upload_dance():
    recent = g.db.view('danceparty/upload_rate',group=True, group_level=1, stale='update_after', key=request.remote_addr)
    if recent:
        now = time.time()
        if app.config['UPLOAD_RATE_COUNT'] <= \
                len(filter(lambda t: t>(now - app.config['UPLOAD_RATE_PERIOD']), recent.rows[0].value)):
            abort(403)
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
        json_data = dance_json(dance)
        json_data['token'] = dance_owner_token(dance_id)
        return json.jsonify(json_data)


@app.route('/dance/<dance_id>.gif')
def uploaded_file(dance_id):
    if app.debug:
        return send_from_directory(app.config['UPLOAD_FOLDER'], dance_id + '.gif')

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')
