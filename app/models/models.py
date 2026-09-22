from sqlalchemy import Column, Integer, String, Boolean, BigInteger, DateTime, Text, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash, check_password_hash
import re
from datetime import datetime, timezone
import uuid
from app.database import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    first_name = Column(String(80), nullable=True)
    last_name = Column(String(80), nullable=True)
    google_id = Column(String(100), unique=True, nullable=True)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    tokens = Column(BigInteger, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sessions = relationship('UserSession', back_populates='user', cascade='all, delete-orphan')
    documents = relationship('Document', back_populates='user', cascade='all, delete-orphan')
    projects = relationship('Project', secondary='project_users', back_populates='users')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def add_tokens(self, amount: int):
        if self.tokens is None:
            self.tokens = 0
        self.tokens += amount
        return self.tokens

    def deduct_tokens(self, amount: int) -> bool:
        if self.tokens is None:
            self.tokens = 0
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
            'is_admin': self.is_admin,
            'tokens': self.tokens,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class UserSession(Base):
    __tablename__ = 'user_sessions'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    token = Column(String(500), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship('User', back_populates='sessions')


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=True)
    doc_id = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="documents")


def validate_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_password(password: str) -> bool:
    return len(password) >= 8


project_users = Table(
    'project_users',
    Base.metadata,
    Column('project_id', Integer, ForeignKey('projects.id'), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True)
)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    project_name = Column(String(255), nullable=False)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", foreign_keys=[owner_id])

    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship(
        "User",
        secondary=project_users,
        back_populates="projects"
    )

    messages = relationship("Message", back_populates="project", cascade="all, delete-orphan")
    responses = relationship("Response", back_populates="project", cascade="all, delete-orphan")
    paper_bucket = relationship("PaperBucket", back_populates="project", uselist=False, cascade="all, delete-orphan")
    paper = relationship("Paper", back_populates="project", uselist=False, cascade="all, delete-orphan")

    vector_status = Column(String(20), default='not_started')  # not_started, processing, ready, error

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_name': self.project_name,
            'owner_id': self.owner_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'users': [{'id': u.id, 'email': u.email, 'first_name': u.first_name, 'last_name': u.last_name} for u in self.users],
            'vector_status': self.vector_status
        }


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    message_number = Column(Integer, nullable=False)
    message_sender = Column(String(120), nullable=False)
    message_content = Column(Text, nullable=False)
    message_timestamp = Column(DateTime, default=datetime.utcnow)

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    project = relationship("Project", back_populates="messages")

    def to_dict(self):
        return {
            'id': self.id,
            'message_number': self.message_number,
            'message_sender': self.message_sender,
            'message_content': self.message_content,
            'message_timestamp': self.message_timestamp.isoformat() if self.message_timestamp else None,
            'project_id': self.project_id
        }


class Response(Base):
    __tablename__ = "responses"

    id = Column(Integer, primary_key=True, index=True)
    response_id = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True)
    summary = Column(Text, nullable=False)
    response_by = Column(String(120), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    project = relationship("Project", back_populates="responses")

    def to_dict(self):
        return {
            'id': self.id,
            'response_id': self.response_id,
            'summary': self.summary,
            'response_by': self.response_by,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'project_id': self.project_id
        }


class PaperBucket(Base):
    __tablename__ = "paper_buckets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, unique=True)
    paper_ids = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="paper_bucket")

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'paper_ids': self.paper_ids if self.paper_ids else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, unique=True)
    content = Column(Text, nullable=True)  # LaTeX content
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="paper")

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
