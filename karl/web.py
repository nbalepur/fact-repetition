#!/usr/bin/env python
# coding: utf-8

import json
import atexit
import socket
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from dateutil.parser import parse as parse_date
from cachetools import cached, TTLCache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from karl.new_util import ScheduleRequest, Params, User, Fact
from karl.scheduler import MovingAvgScheduler
from user_specific_metrics import get_user_charts, save_chart_and_pdf


app = FastAPI()
scheduler = MovingAvgScheduler(preemptive=False)

def get_sessions():
    hostname = socket.gethostname()
    if hostname.startswith('newspeak'):
        db_host = '/fs/clip-quiz/shifeng/postgres/run'
    elif hostname.startswith('lapine'):
        db_host = '/fs/clip-scratch/shifeng/postgres/run'
    else:
        print('unrecognized hostname')
        exit()
    engines = {
        'prod': create_engine(f'postgresql+psycopg2://shifeng@localhost:5433/karl-prod?host={db_host}'),
        'dev': create_engine(f'postgresql+psycopg2://shifeng@localhost:5433/karl-dev?host={db_host}'),
    }
    return {
        env: sessionmaker(bind=engine, autoflush=False)()
        for env, engine in engines.items()
    }


sessions = get_sessions()

# create logger with 'scheduler'
logger = logging.getLogger('scheduler')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('/fs/www-users/shifeng/scheduler.log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)


@app.post('/api/karl/schedule')
def schedule(requests: List[ScheduleRequest]):
    if len(requests) == 0:
        return {
            'order': [],
            'rationale': '<p>no fact received</p>',
            'facts_info': '',
        }

    logger.info(f'/karl/schedule with {len(requests)} facts and env={requests[0].env}')

    # NOTE assuming single user single date
    date = parse_date(datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z'))
    if requests[0].date is not None:
        date = parse_date(requests[0].date)

    env = 'dev' if requests[0].env == 'dev' else 'prod'

    try:
        results = scheduler.schedule(sessions[env], requests, date, plot=False)
        return {
            'order': results['order'],
            'rationale': results['rationale'],
            'facts_info': results['facts_info'],
            # 'profile': results['profile'],
        }
    except SQLAlchemyError as e:
        print(repr(e))
        sessions[env].rollback()
        raise HTTPException(status_code=404, detail='Scheduling failed due to SQLAlchemyError.')


@app.post('/api/karl/update')
def update(requests: List[ScheduleRequest], response_model=bool):
    logger.info(f'/karl/update with {len(requests)} facts and env={requests[0].env}')

    # NOTE assuming single user single date
    date = parse_date(datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z'))
    if requests[0].date is not None:
        date = parse_date(requests[0].date)

    env = 'dev' if requests[0].env == 'dev' else 'prod'

    try:
        scheduler.update(sessions[env], requests, date)
        sessions[env].commit()
        return True
    except SQLAlchemyError as e:
        print(repr(e))
        sessions[env].rollback()
        raise HTTPException(status_code=404, detail='Update failed due to SQLAlchemyError.')


@app.put('/api/karl/set_params', response_model=Params)
def set_params(user_id: str, env: str, params: Params):
    env = 'dev' if env == 'dev' else 'prod'
    session = sessions[env]
    try:
        scheduler.set_user_params(session, user_id, params)
        session.commit()
        return params
    except SQLAlchemyError as e:
        print(repr(e))
        session.rollback()
        raise HTTPException(status_code=404, detail='Set_params failed due to SQLAlchemyError.')


@app.put('/api/karl/set_repetition_model', response_model=Params)
def set_repetition_model(user_id: str, env: str, repetition_model: str):
    env = 'dev' if env == 'dev' else 'prod'
    session = sessions[env]
    if repetition_model == 'sm2':
        params = Params(
            repetition_model='sm2',
            qrep=0,
            skill=0,
            recall=0,
            category=0,
            answer=0,
            leitner=0,
            sm2=1,
            cool_down=0,
        )
        scheduler.set_user_params(session, user_id, params)
        session.commit()
        return params
    elif repetition_model == 'leitner':
        params = Params(
            repetition_model='leitner',
            qrep=0,
            skill=0,
            recall=0,
            category=0,
            answer=0,
            leitner=1,
            sm2=0,
            cool_down=0,
        )
        scheduler.set_user_params(session, user_id, params)
        session.commit()
        return params
    elif repetition_model.startswith('karl'):
        recall_target = int(repetition_model[4:])
        params = Params(
            repetition_model=f'karl{recall_target}',
            qrep=1,
            skill=0,
            recall=1,
            category=1,
            answer=1,
            leitner=1,
            sm2=0,
            recall_target=float(recall_target) / 100,
        )
        scheduler.set_user_params(session, user_id, params)
        session.commit()
        return params
    else:
        raise HTTPException(status_code=404, detail='Unrecognized repetition model.')


@app.post('/api/karl/get_fact', response_model=dict)
def get_fact(fact_id: str, env: str):
    env = 'dev' if env == 'dev' else 'prod'
    fact = sessions[env].query(Fact).get(fact_id)
    if fact is None:
        return
    return json.dumps({
        k: v for k, v in fact.__dict__.items() if k != '_sa_instance_state'
    })


@app.get('/api/karl/reset_user', response_model=dict)
def reset_user(user_id: str = None, env: str = None):
    env = 'dev' if env == 'dev' else 'prod'
    try:
        scheduler.reset_user(sessions[env], user_id=user_id)
        sessions[env].commit()
        return get_user(user_id, env)
    except SQLAlchemyError as e:
        print(repr(e))
        sessions[env].rollback()
        raise HTTPException(status_code=404, detail='Reset user failed.')


@app.get('/api/karl/reset_fact', response_model=dict)
def reset_fact(fact_id: str = None, env: str = None):
    env = 'dev' if env == 'dev' else 'prod'
    try:
        scheduler.reset_fact(sessions[env], fact_id=fact_id)
        sessions[env].commit()
        return get_fact(fact_id, env)
    except SQLAlchemyError as e:
        print(repr(e))
        sessions[env].rollback()


@app.get('/api/karl/status')
def status():
    return True


@app.get('/api/karl/get_user')
def get_user(user_id: str, env: str = None):
    env = 'dev' if env == 'dev' else 'prod'
    user = scheduler.get_user(sessions[env], user_id)
    user_dict = {
        k: v for k, v in user.__dict__.items()
        if k != '_sa_instance_state'
    }
    user_dict['params'] = user_dict['params'].__dict__
    return json.dumps(user_dict)


# @app.get('/api/karl/get_user_history', response_model=List[dict])
def get_user_history(user_id: str, env: str = None, deck_id: str = None,
                     date_start: str = None, date_end: str = None):
    env = 'dev' if env == 'dev' else 'prod'
    return scheduler.get_records(sessions[env], user_id, deck_id, date_start, date_end)


@app.get('/api/karl/get_user_stats', response_model=dict)
# @cached(cache=TTLCache(maxsize=1024, ttl=600))
def get_user_stats(user_id: str, env: str = None, deck_id: str = None,
                   date_start: str = None, date_end: str = None):
    '''
    Return in a dictionary the following user stats within given date range.

    new_facts: int
    reviewed_facts: int
    total_seen: int
    total_seconds: int
    known_rate: float
    new_known_rate: float
    review_known_rate: float
    '''
    env = 'dev' if env == 'dev' else 'prod'
    return scheduler.get_user_stats(sessions[env], user_id, deck_id, date_start, date_end)

class IntOrFloat:

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, float) or isinstance(v, int):
            return v
        raise TypeError('int or float required')


class Ranking(BaseModel):
    user_id: int
    rank: int
    # value: Union[int, float]  # don't use this
    value: IntOrFloat


class Leaderboard(BaseModel):
    leaderboard: List[Ranking]
    total: int
    rank_type: str
    user_place: Optional[int] = None
    user_id: Optional[str] = None
    skip: Optional[int] = 0
    limit: Optional[int] = None


@app.get('/api/karl/leaderboard', response_model=Leaderboard)
# @cached(cache=TTLCache(maxsize=1024, ttl=1800))
def leaderboard(
        user_id: str = None,
        env: str = None,
        skip: int = 0,
        limit: int = 10,
        rank_type: str = 'total_seen',
        min_studied: int = 0,
        deck_id: str = None,
        date_start: str = None,
        date_end: str = None,
):
    '''
    return [(user_id: str, rank_type: 'total_seen', value: 'value')]
    that ranks [skip: skip + limit)
    '''
    env = 'dev' if env == 'dev' else 'prod'

    stats = {}
    for user in scheduler.get_all_users(sessions[env]):
        if not user.user_id.isdigit():
            continue

        stats[user.user_id] = get_user_stats(
            user_id=user.user_id,
            env=env,
            deck_id=deck_id,
            date_start=date_start,
            date_end=date_end
        )

    # profile_keys = [
    #     'profile_get_history_records',
    #     'profile_compute_stats',
    #     'profile_n_history_records',
    # ]
    # profile = {
    #     key: np.sum([v[key] for v in stats.values()])
    #     for key in profile_keys
    # }

    # from high value to low
    stats = sorted(stats.items(), key=lambda x: x[1][rank_type])[::-1]
    stats = [(k, v) for k, v in stats if v['total_seen'] >= min_studied]

    rankings = []
    user_place = None
    for i, (k, v) in enumerate(stats):
        if user_id == k:
            user_place = i
        rankings.append(Ranking(user_id=k, rank=i + 1, value=v[rank_type]))

    leaderboard = Leaderboard(
        leaderboard=rankings[skip: skip + limit],
        total=len(rankings),
        rank_type=rank_type,
        user_place=user_place,
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    # pprint(profile)
    return leaderboard


@app.get('/api/karl/user_charts')
def user_charts(user_id: str, env: str = None):
    env = 'dev' if env == 'dev' else 'prod'
    user = sessions[env].query(User).get(user_id)
    if user is None:
        return

    charts = get_user_charts(user)  # chart_name -> chart
    figure_paths = {}

    figure_dir = '/fs/www-users/shifeng/karl/user_charts'
    for chart_name, chart in charts.items():
        figure_paths[chart_name] = f'{figure_dir}/{user.user_id}_{chart_name}.json'
        chart.save(figure_paths[chart_name])

    return json.dumps(figure_paths)