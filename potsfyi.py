from flask import Flask, request, render_template
from flask.ext.sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tracks.db'
app.config['MUSIC_DIR'] = 'static/music'
db = SQLAlchemy(app)


class Track(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    artist = db.Column(db.String(200))
    title = db.Column(db.String(240))
    filename = db.Column(db.String(256))

    def __init__(self, artist, title, filename):
        self.artist, self.title, self.filename = artist, title, filename

    def __repr__(self):
        return '<Track {0.artist} - {1.title}>'.format(self)


@app.route('/player')
def player_page():
    track_url = request.args.get('track_url', '')
    if track_url == '':
        return 'Not found', 404
    return render_template('player.html',
                           track_url = app.config['MUSIC_DIR'] \
                                   + '/' + track_url)

if __name__ == '__main__':
    app.run()
