from os import environ
from time import sleep
import typing
import json
from threading import Thread
import requests
from flask import Flask, request, make_response, Response
import logging

app = Flask(__name__)
mg_api = "https://api.mailgun.net/v3/mg.oneadame.com/messages"
gre_api = "https://www.google.com/recaptcha/api/siteverify"
secrets = json.loads(environ["api"])

logging.basicConfig(level=logging.INFO)


def retry(
    function: typing.Callable, tries: int = 2, backoff: int = 2
) -> typing.Callable:
    """retry loop with exponential backoff"""

    if environ["ENV"] in ("TEST", "STAGE"):
        tries = 1
        backoff = 1

    def loop(*args, **kwargs):
        for attempt in range(1, tries + 1):

            try:
                return function(*args, **kwargs)

            except Exception as error:
                print(f"exception, {error}")
                if attempt < tries:
                    sleep_for = backoff ** attempt
                    logging.warning(
                        "Connection failed, sleeping for %s seconds\nError message: %s",
                        sleep_for,
                        error,
                    )
                    sleep(sleep_for)
                else:
                    message = f"Failed to connect. Error message: {error}"
                    logging.error(message)

    return loop


class ValidateAndSend:
    """validate grecaptcha, send email"""

    def __init__(self, data):
        self.data = data

        validated_token = self.verify_gre_token()
        if bool(validated_token):
            self.send_mg_email()

    @retry
    def send_mg_email(self) -> bool:
        req = requests.post(
            mg_api,
            auth=("api", secrets["mailgun"]),
            data={
                "from": "website form submission <formsubmission@oneadame.com>",
                "to": secrets["email_recipients"],
                "subject": f"EMAIL FORM SUBMISSION FROM {self.data['email']}",
                "text": self.data["message"],
            },
        )
        req.raise_for_status()

    @retry
    def verify_gre_token(self) -> bool:
        req = requests.post(
            gre_api,
            params={"secret": secrets["grecaptcha"], "response": self.data["token"]},
        )
        req.raise_for_status()
        resp = req.json()
        logging.info(f"Processed grecaptcha with outcome\n{resp}")
        return resp["success"]


def make_cors_response(code: int, data: dict = {}) -> Response:

    cors_headers = {
        "Access-Control-Allow-Origin": [
            "https://oneadame.com",
        ],
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    if code == 204:
        resp = make_response("", 204)
    else:
        resp = make_response(data, code)

    resp.headers.update(cors_headers)
    return resp


@app.route("/email", methods=["POST", "OPTIONS"])
def email_handler():

    # handle preflight requests
    if request.method == "OPTIONS":
        return make_cors_response(200)

    # unparsable
    try:
        data = json.loads(request.data)
    except json.decoder.JSONDecodeError:
        return make_cors_response(400, data={"message": "Bad request."})

    # missing required fields
    required = ("email", "token", "message")
    for e in required:
        if e not in data.keys():
            return make_cors_response(400, data={"message": f"Request missing {e}."})

    # grepatcha and send email on a separate
    # thread to prevent HTTP blocking of response
    complete_request = Thread(target=ValidateAndSend, args=(data,))
    complete_request.start()

    return make_cors_response(204)


@app.route("/heartbeat", methods=["GET"])
def heartbeat_handler():
    return {}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0")
