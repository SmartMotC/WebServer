from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime

# БД 1: пользователи
user_engine = create_engine("sqlite:///./users.db", connect_args={"check_same_thread": False})
UserBase = declarative_base()
UserSessionLocal = sessionmaker(bind=user_engine)


class User(UserBase):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    grade = Column(Integer)


# БД 2: голосования + мемы
votes_engine = create_engine("sqlite:///./votes.db", connect_args={"check_same_thread": False})
VotesBase = declarative_base()
VotesSessionLocal = sessionmaker(bind=votes_engine)


class Vote(VotesBase):
    __tablename__ = "votes"
    id = Column(Integer, primary_key=True)
    category = Column(String(50))
    photo1_path = Column(String(255))
    photo2_path = Column(String(255), nullable=True)
    photo3_path = Column(String(255), nullable=True)
    ip_address = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    results = relationship("VoteResult", back_populates="vote")
    likes = relationship("MemeLike", back_populates="meme")


class VoteResult(VotesBase):
    __tablename__ = "vote_results"
    id = Column(Integer, primary_key=True)
    vote_id = Column(Integer, ForeignKey("votes.id"), nullable=False)
    user_id = Column(Integer, nullable=True)
    photo_choice = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    vote = relationship("Vote", back_populates="results")


class MemeLike(VotesBase):
    __tablename__ = "meme_likes"
    id = Column(Integer, primary_key=True)
    meme_id = Column(Integer, ForeignKey("votes.id"), nullable=False)
    user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    meme = relationship("Vote", back_populates="likes")


def create_all_databases():
    UserBase.metadata.create_all(bind=user_engine)
    VotesBase.metadata.create_all(bind=votes_engine)
    print("Базы данных созданы")


def get_db():
    db = UserSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_votes_db():
    db = VotesSessionLocal()
    try:
        yield db
    finally:
        db.close()


create_all_databases()