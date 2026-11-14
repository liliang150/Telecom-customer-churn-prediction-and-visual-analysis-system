from backend.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("secret123")
    second = hash_password("secret123")
    assert first != second
    assert verify_password("secret123", first)
    assert not verify_password("wrong", first)


def test_access_token_round_trip():
    token = create_access_token("admin", "admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"
