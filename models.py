from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()

class MovieCache(db.Model):
    path = db.Column(db.String, primary_key=True)
    tmdb_id = db.Column(db.Integer)
    title = db.Column(db.String)
    year = db.Column(db.String(8))
    poster = db.Column(db.Boolean, default=False)
    fanart = db.Column(db.Boolean, default=False)
    nfo = db.Column(db.Boolean, default=False)
    last_error = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'path': self.path,
            'tmdb_id': self.tmdb_id,
            'title': self.title,
            'year': self.year,
            'poster': self.poster,
            'fanart': self.fanart,
            'nfo': self.nfo,
            'last_error': self.last_error,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
