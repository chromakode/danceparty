from flask import Flask

app = Flask(__name__)
app.config.from_object('danceparty.default_settings')
app.config.from_envvar('DANCEPARTY_SETTINGS')

import main
