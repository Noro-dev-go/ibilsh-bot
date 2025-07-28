
import psycopg2
from os import getenv


def get_connection():
    return psycopg2.connect(getenv("DB_URL"))
