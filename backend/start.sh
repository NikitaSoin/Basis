#!/bin/bash
alembic upgrade head
python -m scripts.import_profiles_to_db --all
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
