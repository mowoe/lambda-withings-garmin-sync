import requests
from loguru import logger
import time

redirect_uri = "http://127.0.0.1?code=value"

WITHINGS_CLIENT_ID = input("Withings API Client ID? ")
WITHINGS_SECRET = input("Withing API Secret? ")

logger.info("Authenticating using OAuth...")
redirect_url = f"https://account.withings.com/oauth2_user/authorize2?response_type=code&client_id={WITHINGS_CLIENT_ID}&scope=user.info,user.metrics,user.activity&redirect_uri={redirect_uri}&state=dummy-state"
authcode = input("Please enter authcode. Go to this link: " + redirect_url + "\n")

resp = requests.post(
    "https://wbsapi.withings.net/v2/oauth2",
    data={
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": WITHINGS_CLIENT_ID,
        "client_secret": WITHINGS_SECRET,
        "code": authcode,
        "redirect_uri": redirect_uri,
    },
)
resp.raise_for_status()
logger.info(resp.json())

token = resp.json()["body"]["access_token"]
refresh_token = resp.json()["body"]["refresh_token"]
expires_in = resp.json()["body"]["expires_in"]

logger.info(f"token: {token}")
logger.info(f"refresh_token: {refresh_token}")
logger.info(f"valid_until: {int(time.time())+expires_in}")