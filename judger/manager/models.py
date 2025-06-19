from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import String
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class Task(db.Model):
    __tablename__ = 'tasks'

    id: Mapped[int] = mapped_column(primary_key=True)
    judgment_id: Mapped[int] = mapped_column(nullable=False)


class Executor(db.Model):
    __tablename__ = 'executors'

    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(45), nullable=False, unique=True)
    data: Mapped[str] = mapped_column(nullable=False)
    last_updated: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)
    idle: Mapped[bool] = mapped_column(default=True)  # 节点空闲状态

    def __repr__(self):
        return f'<Executor {self.ip}>'
