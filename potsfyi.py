#!/usr/bin/env python
import os
import re
import sys
from subprocess import Popen, PIPE
from flask import (Flask, request, render_template, jsonify, abort, redirect,
                   Response, url_for)
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import (LoginManager, UserMixin, current_user,
                             login_required)
from flask.ext.browserid import BrowserID
from wsgi_utils import PipeWrapper


# Insecure, from the Flask manual - for testing and development only.
DEFAULT_SECRET_KEY = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tracks.db'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 10
db = SQLAlchemy(app)

app.config.update(
    DEBUG=(True if os.environ.get('DEBUG') in ['1', 'True'] else False),
    PORT=int(os.environ.get('PORT', 5000)),
    DB_URI=(os.environ.get('DB_URI', 'sqlite:///tracks.db')),
    MUSIC_DIR=(os.environ.get('MUSIC_DIR', 'static/music')),
    ADMIN_EMAIL=(os.environ.get('ADMIN_EMAIL', None)),
)

app.secret_key = os.environ.get('SECRET_KEY', DEFAULT_SECRET_KEY)
if app.secret_key == DEFAULT_SECRET_KEY:
    if app.config['DEBUG']:
        sys.stderr.write("Warning: using default (insecure) secret key.\n")
    else:
        sys.stderr.write("Error: You need to specify a SECRET_KEY\n")
        sys.exit(1)


class User(UserMixin):
    def __init__(self, user_id):
        UserMixin.__init__(self)
        self.user_id = user_id
        self.admin = (self.user_id == app.config['ADMIN_EMAIL'])

    def get_id(self):
        return unicode(self.user_id)


def get_user_by_id(user_id):
    return User(user_id)


def get_user(resp):
    """ Return a User object based on a BrowserID response. """
    if resp['status'] != 'okay':
        return None  # Login failed for some reason

    # If an admin email is set, and the BrowserID login doesn't match,
    # deny access.
    if (app.config['ADMIN_EMAIL'] and
            app.config['ADMIN_EMAIL'] != resp['email']):
        return None

    return User(resp['email'])  # Either admin, or anyone is allowed.


login_manager = LoginManager()
login_manager.user_loader(get_user_by_id)
login_manager.login_view = "login_view"
login_manager.setup_app(app)

browser_id = BrowserID()
browser_id.user_loader(get_user)
browser_id.init_app(app)


class Track(db.Model):
    ''' artist, track, filename, album '''
    id = db.Column(db.Integer, primary_key=True)
    artist = db.Column(db.String(200))
    title = db.Column(db.String(240))
    filename = db.Column(db.String(256))
    track_num = db.Column(db.Integer)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'))
    album = db.relationship('Album',
        backref=db.backref('tracks', lazy='dynamic'))

    def __init__(self, artist, title, filename, album, track_num):
        self.artist = artist
        self.title = title
        self.album = album
        self.filename = filename
        self.track_num = track_num

    def __repr__(self):
        return u'<Track {0.artist} - {0.title}>'.format(self)

    @property
    def serialize(self):
        return {
            'artist': self.artist,
            'title': self.title,
            'album': self.album.serialize if self.album else '',
            'track': self.track_num,
            'id': self.id
        }


class Album(db.Model):
    ''' artist, title, date, label, cat# '''
    id = db.Column(db.Integer, primary_key=True)
    artist = db.Column(db.String(200))
    title = db.Column(db.String(240))
    # date format?
    date = db.Column(db.String(16))
    label = db.Column(db.String(240))
    cat_number = db.Column(db.String(32))
    cover_art = db.Column(db.String(256))  # filename of cover art, jpg/png

    def __init__(self, artist, title, date=None, label=None, cat_number=None,
                 cover_art=None):
        self.artist = artist
        self.title = title
        self.date = date
        self.label = label
        self.cat_number = cat_number
        self.cover_art = cover_art

    def __repr__(self):
        return (u'<Album {0.title} - ' +
            u'{0.artist} ({0.date})>').format(self)

    @property
    def serialize(self):
        return {
            'artist': self.artist,
            'title': self.title,
            'date': self.date,
            'label': self.label,
            'cat_number': self.cat_number,
            'has_cover_art': self.cover_art is not None,
            'id': self.id
        }


@app.route('/search')
@login_required
def search_results():
    """ Perform a general search encompassing artist, track, albums. """
    search_term = request.args.get('q', '')

    # split search term into up to 10 tokens (anything further is ignored)
    tokens = filter(None, re.split('\s+', search_term))[:10]

    filters = [Track.title.contains(token) | Track.artist.contains(token)
               for token in tokens]
    tracks = Track.query.filter(*filters).limit(30).all()

    album_filters = [Album.title.contains(token) |
                     Album.artist.contains(token) for token in tokens]
    albums = Album.query.filter(*album_filters).limit(10).all()

    return jsonify(objects=[t.serialize for t in (albums + tracks)])


@app.route('/album/<int:album_id>')
@login_required
def list_album(album_id):
    """ Given an album ID, list its tracks. """
    tracks = Track.query.filter_by(album_id=album_id)\
                        .order_by(Track.track_num)
    return jsonify(objects=[t.serialize for t in tracks])


@app.route('/song/<int:track_id>/<wanted_formats>')
@login_required
def get_track(track_id, wanted_formats):
    """ Get a track.
    If `wanted_formats` (a comma-separated list) includes the file's actual
    format, a redirect is sent (so the static file can be handled as such).
    Otherwise, if `wanted_formats` includes ogg, it's transcoded on the fly.
    """

    TRANSCODABLE_FORMATS = ['mp3', 'ogg', 'flac', 'm4a', 'wav']
    wanted_formats = re.split(',', wanted_formats)

    track = Track.query.filter_by(id=track_id).first()
    if track is None:
        abort(404)

    actual_format = re.search('\.([^.]+)$', track.filename).group(1)
    if actual_format in wanted_formats:
        # No need to transcode. Just redirect to the static file.
        return redirect(os.path.join('/' + app.config['MUSIC_DIR'],
                                     track.filename))

    if (actual_format not in TRANSCODABLE_FORMATS
            or 'ogg' not in wanted_formats):
        # Can't transcode this. We only go from TRANSCODABLE_FORMATS to ogg.
        abort(404)

    # Transcode to ogg.
    # Note that track.filename came out of the DB and is *not* user-specified
    # (through the web interface), so can be trusted.
    command = ['avconv', '-v', 'quiet',
               '-i', os.path.join(app.config['MUSIC_DIR'], track.filename),
               '-f', 'ogg', '-acodec', 'libvorbis', '-aq', '5', '-']
    pipe = Popen(command, stdout=PIPE)

    return Response(PipeWrapper(pipe),
                    mimetype='audio/ogg', direct_passthrough=True)


@app.route('/albumart/<int:album_id>')
@login_required
def get_album_art(album_id):
    album = Album.query.filter_by(id=album_id).first()
    if album is None or album.cover_art is None:
        abort(404)
    return redirect(os.path.join('/' + app.config['MUSIC_DIR'],
                                 album.cover_art))


@app.route('/')
@login_required
def front_page():
    return render_template('app.html')


@app.route('/login')
def login_view():
    if current_user.is_authenticated():
        return redirect(url_for('front_page'))
    return render_template('login.html')

if __name__ == '__main__':
    app.run(port=app.config['PORT'])
