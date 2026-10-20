import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "claim_app.settings")

from claim_app.wsgi import application  # noqa: E402,F401
