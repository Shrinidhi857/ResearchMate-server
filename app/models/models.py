from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import re
from datetime import datetime, timedelta, timezone
import uuid
from app.extensions import db



class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    tokens = db.Column(db.BigInteger, default=0)  
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def add_tokens(self, amount: int):
        self.tokens += amount
        return self.tokens

    def deduct_tokens(self, amount: int):
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'is_verified': self.is_verified,
            'tokens': self.tokens,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class UserSession(db.Model):
    __tablename__ = 'user_sessions'   
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(500), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('sessions', lazy=True))



class Document(db.Model):
    __tablename__ = "documents"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=True)  # use title instead of name
    doc_id = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = db.Column(db.Text, nullable=False)  # PDF text content
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("documents", lazy=True))

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    return len(password) >= 8     

project_users = db.Table(
    'project_users',
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id')),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'))
)


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)
    project_name = db.Column(db.String(255), nullable=False)

    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    owner = db.relationship("User")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship(
        "User",
        secondary=project_users,
        backref=db.backref("projects", lazy=True)
    )

    messages = db.relationship("Message", backref="project", cascade="all, delete-orphan")
    responses = db.relationship("Response", backref="project", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_name': self.project_name,
            'owner_id': self.owner_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'users': [{'id': u.id, 'email': u.email, 'first_name': u.first_name, 'last_name': u.last_name} for u in self.users]
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    message_number = db.Column(db.Integer, nullable=False)
    message_sender = db.Column(db.String(120), nullable=False)
    message_content = db.Column(db.Text, nullable=False)
    message_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'message_number': self.message_number,
            'message_sender': self.message_sender,
            'message_content': self.message_content,
            'message_timestamp': self.message_timestamp.isoformat() if self.message_timestamp else None,
            'project_id': self.project_id
        }

class Response(db.Model):
    __tablename__ = "responses"

    id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)
    summary = db.Column(db.Text, nullable=False)
    response_by = db.Column(db.String(120), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'response_id': self.response_id,
            'summary': self.summary,
            'response_by': self.response_by,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'project_id': self.project_id
        }


class PaperBucket(db.Model):
    __tablename__ = "paper_buckets"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, unique=True)
    paper_ids = db.Column(db.JSON, default=list, nullable=False)  # Store array of paper/document IDs
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship("Project", backref=db.backref("paper_bucket", uselist=False, cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'paper_ids': self.paper_ids if self.paper_ids else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Paper(db.Model):
    __tablename__ = "papers"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, unique=True)
    content = db.Column(db.Text, nullable=True)  # LaTeX content
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship("Project", backref=db.backref("paper", uselist=False, cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
