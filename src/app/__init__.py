import os
import json
from flask import Flask
# from flask.ext.script import Manager
# from flask.ext.sqlalchemy import SQLAlchemy
# from flask.ext.migrate import Migrate, MigrateCommand


app = Flask(__name__)

# configuration
app.config.from_object('app.config.Dev')

# database
# app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://speler:spe1er@db:5432/musiek'
# db = SQLAlchemy(app)

# migrations
# migrate = Migrate(app, db)

# json encoding
# from app.json_encoder import AlchemyEncoder
# app.json_encoder = AlchemyEncoder

# load routing
from app import views

# create manager
# manager = Manager(app)
# manager.add_command('db', MigrateCommand)

