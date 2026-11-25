"""Entry point.  Dev: python run.py    Prod: gunicorn -w 1 --threads 8 'run:app'  (SQLite => keep a single worker)."""
import os

from itamx.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("ITAMX_HOST", "0.0.0.0"), port=int(os.environ.get("ITAMX_PORT", "8080")))
