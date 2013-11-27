import cStringIO
import hashlib
import os
import random
import uuid

from PIL import Image
from flask import request, render_template, send_from_directory

from danceparty import app


def check_gif(data):
    img_stream = cStringIO.StringIO(data)
    # Confirm it is a GIF first.
    try:
        img = Image.open(img_stream)
        if img.format !='GIF':
            return False
    except IOError:
        return False
    #Loop through its frames adding up delays untill we run out of frames or exceed 1 second.
    #Note that PIL uses seek and tell for frames. I have no idea why.
    #It would be nice to iterate over them, but it seems there is just an exception at the end.
    duration = img.info['duration']
    try:
        #Go through frames summing the durations untill we run out of ms in the second limit. (or, an extra frame)
        while duration <= 1050:
            img.seek(img.tell()+1)
            duration += img.info['duration']
        #If we leave the while loop without an error, we exceeded the time bound.
        return False
    #We reached the last frame without exceeding the while loops ms time bound.
    except EOFError:
        return True

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
