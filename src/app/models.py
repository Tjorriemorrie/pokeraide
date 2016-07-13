from app import app, db
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
import datetime


class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    abs_path = db.Column(db.String(255), unique=True)
    web_path = db.Column(db.String(255), unique=True)
    path_name = db.Column(db.String(255), unique=True)

    # info
    id3_parsed = db.Column(db.Boolean, server_default=u'false')
    name = db.Column(db.String(255))
    track_number = db.Column(db.Integer)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'))
    album = db.relationship('Album', lazy='joined', cascade='all, delete-orphan', single_parent=True)
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id'))
    artist = db.relationship('Artist', lazy='joined', cascade='all, delete-orphan', single_parent=True)

    # plays
    queue = db.relation('Queue', cascade="all, delete-orphan")
    count_played = db.Column(db.Integer, server_default=u'0', nullable=False)
    played_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    histories = db.relationship('History', cascade="all, delete-orphan")
    # ratings
    ratings_winners = db.relationship('Rating', backref='song_winner', foreign_keys='Rating.song_winner_id', cascade="all, delete-orphan")
    ratings_losers = db.relationship('Rating', backref='song_loser', foreign_keys='Rating.song_loser_id', cascade="all, delete-orphan")
    rated_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    count_rated = db.Column(db.Integer, server_default=u'0', nullable=False)
    rating = db.Column(db.Float, default=0.5, nullable=False)
    # other
    priority = db.Column(db.Float, nullable=False)
    days_since_played = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __init__(self, path):
        self.abs_path = path
        self.web_path = path[9:]
        self.path_name = self.web_path[len('/static/music/'):]
        self.priority = 0.5
        self.days_since_played = 7

    @hybrid_property
    def days_since_rated(self):
        return (datetime.datetime.now() - self.rated_at).days

    @days_since_rated.expression
    def days_since_rated(cls):
        return db.func.extract(db.text('DAY'), db.func.now() - cls.rated_at)

    @hybrid_property
    def selection_weight(self):
        return (self.priority * 1.0) + (self.days_since_rated / float(self.days_since_played))

    @selection_weight.expression
    def selection_weight(cls):
        return (cls.priority * 1.0) + (cls.days_since_rated / db.func.cast(cls.days_since_played, db.Float))

    def __json__(self):
        return [
            'id', 'path_name', 'web_path',
            'name', 'track_number',
            'count_played', 'count_rated', 'rating',
            'priority', 'played_at',
            'artist', 'album'
        ]

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.id)


class Album(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    name_id = db.Column(db.String(255), nullable=False)
    total_tracks = db.Column(db.Integer)
    year = db.Column(db.Integer)
    disc_number = db.Column(db.Integer, server_default=u'1')
    total_discs = db.Column(db.Integer, server_default=u'1')

    songs = db.relationship('Song', lazy="joined")
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id'))
    artist = db.relationship('Artist', lazy='joined', cascade='all, delete-orphan', single_parent=True)

    count_songs = db.Column(db.Integer)
    count_played = db.Column(db.Integer)
    played_at = db.Column(db.DateTime, server_default=db.func.now())
    count_rated = db.Column(db.Integer)
    rated_at = db.Column(db.DateTime, server_default=db.func.now())
    rating = db.Column(db.Float)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __init__(self, name, artist):
        self.name = name
        self.name_id = name.lower().strip()
        self.artist = artist

    def __json__(self):
        return [
            'id', 'name', 'total_tracks', 'disc_number', 'year',
            'artist', 'count_songs',
            'count_played', 'played_at',
            'count_rated', 'rated_at', 'rating',
        ]

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.id)


class Artist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True)
    name_id = db.Column(db.String(255), unique=True)
    songs = db.relationship('Song', lazy="joined")
    albums = db.relationship('Album', lazy="joined")

    count_songs = db.Column(db.Integer)
    count_albums = db.Column(db.Integer)
    count_played = db.Column(db.Integer)
    played_at = db.Column(db.DateTime, server_default=db.func.now())
    count_rated = db.Column(db.Integer)
    rated_at = db.Column(db.DateTime, server_default=db.func.now())
    rating = db.Column(db.Float)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __init__(self, name):
        self.name = name
        self.name_id = name.lower().strip()

    def __json__(self):
        return [
            'id', 'name',
            'count_songs', 'count_albums',
            'count_played', 'played_at',
            'count_rated', 'rated_at', 'rating',
        ]

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.id)


class Queue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), unique=True, nullable=False)
    song = db.relationship('Song', lazy='joined')
    src = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __init__(self, song):
        self.song = song
        self.src = song.web_path

    def __json__(self):
        return ['id', 'song', 'src']

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.id)


class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), nullable=False)
    song = db.relationship('Song', lazy='joined')
    played_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __init__(self, song):
        self.song = song

    def __json__(self):
        return ['id', 'song', 'played_at']

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.id)


class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    song_winner_id = db.Column(db.Integer, db.ForeignKey('song.id'))
    # song = db.relationship('Song', lazy='joined')
    song_loser_id = db.Column(db.Integer, db.ForeignKey('song.id'))
    rated_at = db.Column(db.DateTime, server_default=db.func.now())
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __init__(self, winner, loser):
        self.song_winner = winner
        self.song_loser = loser

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.id)

