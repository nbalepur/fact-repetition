import json
import numpy as np
import msgpack
import msgpack_numpy
from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date
from sqlalchemy import ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import MutableDict, MutableList
import sqlalchemy.types as types

from karl.util import Params

Base = declarative_base()

class JSONEncoded(types.TypeDecorator):

    impl = types.VARCHAR

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


class ParamsType(types.TypeDecorator):

    impl = types.VARCHAR

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps({k: v for k, v in value.__dict__.items() if not k.startswith('_')})
        else:
            return json.dumps({k: v for k, v in Params().__dict__.items() if not k.startswith('_')})

    def process_result_value(self, value, dialect):
        return Params(**json.loads(value))


class BinaryNumpy(types.TypeDecorator):

    impl = types.LargeBinary

    def process_bind_param(self, value, dialect):
        return msgpack.packb(value, default=msgpack_numpy.encode)

    def process_result_value(self, value, dialect):
        return msgpack.unpackb(value, object_hook=msgpack_numpy.decode)


class Fact(Base):
    __tablename__ = 'facts'
    fact_id = Column(String, primary_key=True)
    text = Column(String)
    answer = Column(String)
    category = Column(String)
    deck_name = Column(String, default='')
    deck_id = Column(String, default='')
    qrep = Column(BinaryNumpy, default=np.array([]))
    skill = Column(BinaryNumpy, default=np.array([]))
    results = Column(MutableList.as_mutable(JSONEncoded), default=[])


class User(Base):
    __tablename__ = 'users'
    user_id = Column(String, primary_key=True)
    recent_facts = Column(MutableList.as_mutable(JSONEncoded), default=[])
    previous_study = Column(MutableDict.as_mutable(JSONEncoded), default={})
    leitner_box = Column(MutableDict.as_mutable(JSONEncoded), default={})
    leitner_scheduled_date = Column(MutableDict.as_mutable(JSONEncoded), default={})
    sm2_efactor = Column(MutableDict.as_mutable(JSONEncoded), default={})
    sm2_interval = Column(MutableDict.as_mutable(JSONEncoded), default={})
    sm2_repetition = Column(MutableDict.as_mutable(JSONEncoded), default={})
    sm2_scheduled_date = Column(MutableDict.as_mutable(JSONEncoded), default={})
    # for computing user average accuracy
    results = Column(MutableList.as_mutable(JSONEncoded), default=[])
    # qid -> number of times user and qid correctly
    count_correct_before = Column(MutableDict.as_mutable(JSONEncoded), default={})
    # qid -> number of times user and qid incorrectly
    count_wrong_before = Column(MutableDict.as_mutable(JSONEncoded), default={})
    params = Column(ParamsType)


class UserSnapshot(Base):
    __tablename__ = 'user_snapshots'
    debug_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.user_id'))
    record_id = Column(String, ForeignKey('record.record_id'))
    date = Column(DateTime)
    recent_facts = Column(MutableList.as_mutable(JSONEncoded), default=[])
    previous_study = Column(MutableDict.as_mutable(JSONEncoded), default={})
    leitner_box = Column(MutableDict.as_mutable(JSONEncoded), default={})
    leitner_scheduled_date = Column(MutableDict.as_mutable(JSONEncoded), default={})
    sm2_efactor = Column(MutableDict.as_mutable(JSONEncoded), default={})
    sm2_interval = Column(MutableDict.as_mutable(JSONEncoded), default={})
    sm2_repetition = Column(MutableDict.as_mutable(JSONEncoded), default={})
    sm2_scheduled_date = Column(MutableDict.as_mutable(JSONEncoded), default={})
    results = Column(MutableList.as_mutable(JSONEncoded), default=[])
    count_correct_before = Column(MutableDict.as_mutable(JSONEncoded), default={})
    count_wrong_before = Column(MutableDict.as_mutable(JSONEncoded), default={})
    params = Column(ParamsType)

    user = relationship("User", back_populates="user_snapshots")
    record = relationship("Record", back_populates="user_snapshot")


class Record(Base):
    __tablename__ = 'records'
    record_id = Column(String, primary_key=True)
    debug_id = Column(String)
    user_id = Column(String, ForeignKey('users.user_id'))
    fact_id = Column(String, ForeignKey('facts.fact_id'))
    deck_id = Column(String)
    response = Column(Boolean)
    judgement = Column(String)
    fact_ids = Column(String)
    elapsed_seconds_text = Column(Integer)
    elapsed_seconds_answer = Column(Integer)
    elapsed_milliseconds_text = Column(Integer)
    elapsed_milliseconds_answer = Column(Integer)
    is_new_fact = Column(Boolean)
    date = Column(DateTime)

    user = relationship("User", back_populates="records")
    fact = relationship("Fact", back_populates="records")

    # NOTE we store the following snapshots so that we can jump to anywhere in time 
    # to conduct an intervention on the scheduler 
    # 1) without having to re-compute the whole history of each user, and
    # 2) compare with the scheduler output before the intervention
    user_snapshot = relationship("UserSnapshot", uselist=False, back_populates="record")
    fact_snapshot = relationship("FactSnapshot", uselist=False, back_populates="record")
    scheduler_output = relationship("SchedulerOutput", uselist=False, back_populates="record")


class SchedulerOutput(Base):
    debug_id = Column(String, primary_key=True)
    order = Column(MutableDict.as_mutable(JSONEncoded), default=[])
    scores = Column(MutableDict.as_mutable(JSONEncoded), default=[])
    details = Column(MutableDict.as_mutable(JSONEncoded), default={})
    rationale = Column(String)

    record = relationship('Record', back_populates='scheduler_output')


class FactSnapshot(Base):
    id = Column(Integer , primary_key=True , autoincrement=True)
    # fact_id -> list of binary results
    results = Column(MutableDict.as_mutable(JSONEncoded), default={})
    
    record = relationship('Record', back_populates='fact_snapshot')


class UserStat(Base):
    __tablename__ = 'user_stats'
    user_stat_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.user_id'))
    deck_id = Column(String)
    date = Column(Date)
    new_facts = Column(Integer, default=0)
    reviewed_facts = Column(Integer, default=0)
    new_correct = Column(Integer, default=0)
    reviewed_correct = Column(Integer, default=0)
    total_seen = Column(Integer, default=0)
    total_milliseconds = Column(Integer, default=0)
    total_seconds = Column(Integer, default=0)
    total_minutes = Column(Integer, default=0)
    elapsed_milliseconds_text = Column(Integer, default=0)
    elapsed_milliseconds_answer = Column(Integer, default=0)
    elapsed_seconds_text = Column(Integer, default=0)
    elapsed_seconds_answer = Column(Integer, default=0)
    elapsed_minutes_text = Column(Integer, default=0)
    elapsed_minutes_answer = Column(Integer, default=0)
    n_days_studied = Column(Integer, default=0)

    user = relationship("User", back_populates="user_stats")


User.records = relationship("Record", order_by=Record.date, back_populates="user")
Fact.records = relationship("Record", order_by=Record.date, back_populates="fact")
User.user_stats = relationship("UserStat", order_by=UserStat.date, back_populates="user")
User.user_snapshots = relationship("UserSnapshot", order_by=UserSnapshot.date, back_populates="user")