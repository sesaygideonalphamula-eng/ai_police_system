"""Password hashing and login tokens (Python standard library only)."""
import base64
import hashlib
import hmac
import os
import time

from . import config


def hash_password(password, salt_hex=None):
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return digest.hex(), salt.hex()


def verify_password(password, hash_hex, salt_hex):
    calc, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(calc, hash_hex)


def _sign(text):
    return hmac.new(config.secret_key().encode(), text.encode(), hashlib.sha256).hexdigest()


def make_token(user_id, hours=None):
    hours = hours or config.TOKEN_HOURS
    body = "{}:{}".format(user_id, int(time.time() + hours * 3600))
    b = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return b + "." + _sign(b)


def read_token(token):
    """Return the user id inside a valid, unexpired token, otherwise None."""
    try:
        b, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sign(b)):
            return None
        body = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode()
        uid, exp = body.split(":")
        if int(exp) < time.time():
            return None
        return int(uid)
    except Exception:
        return None
