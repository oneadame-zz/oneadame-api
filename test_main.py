from flask import request
import requests
import logging
import pytest
from main import app, mg_api, gre_api, retry


@pytest.fixture(autouse=True)
def no_external_requests(monkeypatch):
    """Remove requests.sessions.Session.request for all tests."""
    monkeypatch.delattr("requests.sessions.Session.request")


@pytest.fixture()
def client():
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client


class MockApiBaseGood:
    def __init__(self, url: str):
        self.url = url

    @staticmethod
    def raise_for_status():
        return None

    def post(self, url):
        if self.url == mg_api:
            return {"status_code": 200}

    def json(self):
        if self.url == gre_api:
            return {
                "success": True,
                "challenge_ts": "2020-09-08T00:13:34Z",
                "hostname": "localhost",
            }


class MockApiBaseBad(MockApiBaseGood):
    def json(self):
        if self.url == gre_api:
            return {"success": False, "error-codes": ["timeout-or-duplicate"]}


@pytest.fixture
def mock_api(monkeypatch):
    def mock_api(*args, **kwargs):
        return MockApiBaseGood(args[0])

    monkeypatch.setattr(requests, "post", mock_api)


@pytest.fixture
def mock_api_bad(monkeypatch):
    def mock_api(*args, **kwargs):
        return MockApiBaseBad(args[0])

    monkeypatch.setattr(requests, "post", mock_api)


def test_retry(caplog):

    message = "HTTP 500 ERROR"

    @retry
    def error():
        raise ConnectionError(message)

    error()
    assert message in caplog.text


def test_email_missing(client):
    resp = client.post("/email", json={"some": "data"})
    assert resp.json["message"] == "Request missing email."
    assert resp.status_code == 400


def test_email_none(client):
    resp = client.post("/email")
    assert resp.json["message"] == "Bad request."
    assert resp.status_code == 400


def test_email_good(client, mock_api):
    resp = client.post(
        "/email",
        json={
            "email": "eddytest@test.com",
            "message": "This is a cool test message, bye.",
            "token": "recaptchatoken",
        },
    )
    assert resp.status_code == 204


def test_gre_bad(client, mock_api_bad, caplog):
    caplog.set_level(logging.INFO)

    resp = client.post(
        "/email",
        json={
            "email": "eddytest@test.com",
            "message": "A message you will never see, bye.",
            "token": "badrecaptcha",
        },
    )
    assert resp.status_code == 204
    assert "False" in caplog.text
