from app import security


def test_password_hash_roundtrip():
    h, salt = security.hash_password("Commander@123")
    assert security.verify_password("Commander@123", h, salt)
    assert not security.verify_password("WrongPassword", h, salt)


def test_token_roundtrip_and_expiry():
    token = security.make_token(user_id=7)
    assert security.read_token(token) == 7
    assert security.read_token(token + "x") is None
    expired = security.make_token(user_id=7, hours=-1)
    assert security.read_token(expired) is None
