import environ
import os

env = environ.Env()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

env.read_env(os.path.join(BASE_DIR, ".env"))

HOST = env.str("HOST", default="0.0.0.0")
PORT = env.int("PORT", default=8649)

DEBUG = env.bool("DEBUG", default=False)
UTILITARIAN_BASE_URL = env.str("UTILITARIAN_BASE_URL")
UTILITARIAN_API_KEY = env.str("UTILITARIAN_API_KEY")
HTTP_TIMEOUT = env.int("HTTP_TIMEOUT", default=30)
