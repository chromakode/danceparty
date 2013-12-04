#!/usr/bin/python

from danceparty import app
# Chrome with dev tools open deadlocks if threaded=True is not set.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.run(host='0.0.0.0', debug=True, threaded=True, ssl_context='adhoc')
