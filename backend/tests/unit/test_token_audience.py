import pytest
from jose import JWTError

from revenueflowai.auth.oidc import _check_audience


def test_keycloak_style_audience_matches():
    _check_audience({"aud": "revenueflow-backend"}, "revenueflow-backend")


def test_keycloak_style_audience_list_matches():
    _check_audience({"aud": ["account", "revenueflow-backend"]}, "revenueflow-backend")


def test_cognito_access_token_client_id_matches():
    _check_audience({"token_use": "access", "client_id": "abc123"}, "abc123")


def test_other_audience_is_rejected():
    with pytest.raises(JWTError):
        _check_audience({"aud": "some-other-api"}, "revenueflow-backend")


def test_token_without_any_audience_is_rejected():
    with pytest.raises(JWTError):
        _check_audience({"sub": "x"}, "revenueflow-backend")
