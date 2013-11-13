import cStringIO
import hashlib
import os
import random
import uuid

from PIL import Image
from flask import Flask, request, render_template, send_from_directory


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # MB


def check_gif(data):
    img_stream = cStringIO.StringIO(data)
    try:
        img = Image.open(img_stream)
        return img.format =='GIF'
    except IOError:
        return False


@app.route('/')
def dances_plz():
    fs = os.listdir(app.config['UPLOAD_FOLDER'])
    fs.sort()
    dances = random.sample(fs, min(100, len(fs)))
    return render_template('dance.html', dances=dances)


@app.route('/dance/<num>')
def uploaded_file(num):
    return send_from_directory(app.config['UPLOAD_FOLDER'], num)


@app.route('/dance', methods=['POST'])
def upload_dance():
    gif = request.files['moves']
    gif_data = gif.read()
    if gif and check_gif(gif_data):
        name = hashlib.sha1(str(uuid.uuid4())).hexdigest() + '.gif'
        with open(os.path.join(app.config['UPLOAD_FOLDER'], name), 'w') as out:
            out.write(gif_data)
        return 'sweet moves!'


if __name__ == '__main__':
    # Chrome with dev tools open deadlocks if threaded=True is not set.
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    app.run(host='0.0.0.0', debug=True, threaded=True)
