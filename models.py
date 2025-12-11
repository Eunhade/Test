from db import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
   
    total_games = db.Column(db.Integer, default=0, nullable=False)
    total_wins = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password: str):
        """Hash and store password securely."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)
    
    @property
    def win_rate(self) -> float:
        """Calculate win percentage."""
        if self.total_games == 0:
            return 0.0
        return (self.total_wins / self.total_games) * 100

    def __repr__(self):
        return f"<User {self.username}>"

class Match(db.Model):
    __tablename__ = "matches"
    
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(128), nullable=False, index=True)
    
    p1_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    p2_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    score_p1 = db.Column(db.Integer, nullable=False)
    score_p2 = db.Column(db.Integer, nullable=False)
    
    winner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    
    duration = db.Column(db.Integer, nullable=False, default=300)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    player1 = db.relationship("User", foreign_keys=[p1_id])
    player2 = db.relationship("User", foreign_keys=[p2_id])
    winner = db.relationship("User", foreign_keys=[winner_id])

    def __repr__(self):
        return f"<Match {self.room}: {self.p1_id} ({self.score_p1}) vs {self.p2_id} ({self.score_p2})>"
