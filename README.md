# KARL scheduler

Make sure to use `git-lfs` to pull the model checkpoints too alongside the code.

## Install python dependencies
1. If you are using `conda`, consider creating a new environment, and make sure
   to run `conda install pip` so that the following dependencies are installed
   for your environment.
2. It's recommended that you use python 3.11.4
3. Install dependencies with `poetry install`.
4. [Optional] Install Spacy module with `python -m spacy download en_core_web_lg`.
5. Start the poetry shell `poetry shell`.
6. If you see an error related to `psycopg2-binary`, the easiest solution is probably to install it via pip.

## Start PostgreSQL server
1. Use brew to install PostgreSQL 12: `brew install postgresql@12`.
2. The server should automatically start. You can use brew services to manage it, e.g., `brew services stop postgresql@12`.
3. Create DB cluster `initdb`, then create DB `createdb karl-prod`.
4. You may need to modify `alembic.ini` to specify `sqlalchemy.url` to have your name

### load the dev database
1. Restore from dump `gunzip -c data/karl-dev.gz | psql karl-prod

### start from scratch
1. Run `alembic upgrade head`

## Running a test
1. After `poetry shell`, run `python -m karl.tests.test_scheduling_with_session`.

## `dotenv` file
You need a `.env` file in the `karl` directory. Modify `CODE_DIR` as needed and change `shifeng` in `SQLALCHEMY_DATABASE_URL` to your user (check via `SELECT current_user;`). 
Change `API_URL` to match with the `INTERFACE` variable in the app. You may also need to specify a password to your database url.
```
CODE_DIR="/Users/shifeng/workspace/fact-repetition"
# Should match with port defined in INTERFACE in karl app .env 
API_URL="http://0.0.0.0:8000" 
MODEL_API_URL="http://0.0.0.0:8001"
SQLALCHEMY_DATABASE_URL="postgresql+psycopg2://shifeng@localhost:5432/karl-prod"
USE_MULTIPROCESSING=True
MP_CONTEXT="fork"
```

## Figures
1. For figures you might need `vega-lite`. Install with conda: `conda install -c conda-forge vega vega-lite vega-embed vega-lite-cli`.
2. Note, can also be done by doing `npm install -g` for vega, vega-lite, vega-embed, and vega-cli.
