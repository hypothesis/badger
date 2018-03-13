import asyncio
import logging
import re
import os
import sys

from sanic.response import json


def require_env(name, typ):
    val = os.environ.get(name)
    if val is None:
        raise Exception(f'Required environment variable {name} is not set')
    return typ(val)


def optional_env(name, typ, default):
    val = os.environ.get(name)
    if val is None:
        return default
    else:
        return typ(val)


def error_response(msg, status=400):
    return json({'error': msg}, status=status)


def username_from_userid(userid):
    m = re.fullmatch('acct:([^@]+)@[^@]+', userid)
    if m is None:
        return None
    return m.group(1)


# Map of (module path => Logger)
loggers = {}


def get_logger(name):
    logger = loggers.get(name)
    if logger:
        return logger

    # This configures a logger with the standard setup for the app.
    # TODO: This approach is not particularly idiomatic. Can we use logger ancestor
    # relationships instead and just do this configuration for the root logger?

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    stdout_handler.setLevel(logging.INFO)

    logger = logging.getLogger(name)
    logger.addHandler(stdout_handler)
    logger.setLevel(logging.INFO)

    loggers[name] = logger

    return logger


def run_async_task(coro):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(coro)
