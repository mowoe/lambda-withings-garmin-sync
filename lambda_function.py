import requests
import json
from loguru import logger
from datetime import datetime
import pytz
import time
import pprint

from garmin_utils import init_api
import os
import boto3

def handler(event, context):
    GARMIN_CONNECT_EMAIL = os.environ.get("GARMIN_CONNECT_EMAIL",0)
    GARMIN_CONNECT_PASSWORD = os.environ.get("GARMIN_CONNECT_PASSWORD",0)
    if not GARMIN_CONNECT_EMAIL or not GARMIN_CONNECT_PASSWORD:
        raise ValueError("Essential Garmin Connect environment variables missing.")

    s3 = boto3.client('s3')
    bucket_name = os.getenv('BUCKET_NAME', 'withings-garmin-sync-config-bucket')
    config_file_key = 'withings_config.json'

    try:
        response = s3.get_object(Bucket=bucket_name, Key=config_file_key)
        config_content = json.loads(response['Body'].read().decode('utf-8'))
    except s3.exceptions.NoSuchKey:
        logger.warning("This seems to be the first run, writing environment variables to config.json...")

        WITHINGS_ACCESS_TOKEN = os.environ.get("WITHINGS_ACCESS_TOKEN", 0)
        WITHINGS_REFRESH_TOKEN = os.environ.get("WITHINGS_REFRESH_TOKEN", 0)
        WITHINGS_TOKEN_VALID_UNTIL = os.environ.get("WITHINGS_TOKEN_VALID_UNTIL", 0)

        if not WITHINGS_ACCESS_TOKEN or not WITHINGS_REFRESH_TOKEN or not WITHINGS_TOKEN_VALID_UNTIL:
            raise ValueError("Missing essential withings environment variables.")
        
        withings_config = {
            "access_token": WITHINGS_ACCESS_TOKEN,
            "refresh_token": WITHINGS_REFRESH_TOKEN,
            "valid_until": WITHINGS_TOKEN_VALID_UNTIL
        }

        s3.put_object(Bucket=bucket_name, Key=config_file_key, Body=json.dumps(withings_config))

    token = withings_config["access_token"]
    refresh_token = withings_config["refresh_token"]
    valid_until = int(withings_config["valid_until"])

    if valid_until - 100 < int(time.time()):
        WITHINGS_CLIENT_ID = os.environ.get("WITHINGS_CLIENT_ID",0)
        WITHINGS_SECRET = os.environ.get("WITHINGS_SECRET", 0)
        if not WITHINGS_CLIENT_ID or not WITHINGS_SECRET:
            raise ValueError("Missing essential withings api environment variables.")

        logger.info("Token expired, refreshing")
        resp = requests.post(
            "https://wbsapi.withings.net/v2/oauth2",
            data={
                "action": "requesttoken",
                "grant_type": "refresh_token",
                "client_id": WITHINGS_CLIENT_ID,
                "client_secret": WITHINGS_SECRET,
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        
        try:
            token = resp.json()["body"]["access_token"]
            refresh_token = resp.json()["body"]["refresh_token"]
            expires_in = resp.json()["body"]["expires_in"]
        except KeyError:
            logger.error("Error refreshing token")
            logger.error(resp.json())
            exit(1)

        withings_config = {
            "access_token": token,
            "refresh_token": refresh_token,
            "valid_until": int(int(time.time()) + int(expires_in))
        }

        s3.put_object(Bucket=bucket_name, Key=config_file_key, Body=json.dumps(withings_config))
    else:
        logger.info(
            "Token still valid for another "
            + str(valid_until - int(time.time()))
            + " seconds"
        )    



    logger.info("Requesting weight data from Withings...")

    resp = requests.post(
        "https://wbsapi.withings.net/measure",
        headers={"Authorization": f"Bearer {token}"},
        data={"action": "getmeas", "meastypes": "1,5,6,8,76,77,88,168,169,170"},
    )
    resp.raise_for_status()


    tz = pytz.timezone("Europe/Berlin")

    iso_timestamps = []
    withings_measures = []
    for measure in resp.json()["body"]["measuregrps"]:
        datapoint = {}
        for mes in measure["measures"]:
            if mes["type"] == 1:
                key = "weight"
            elif mes["type"] == 5:
                key = "fat_free_mass"
            elif mes["type"] == 8:
                key = "fat_mass_weight"
            elif mes["type"] == 76:
                key = "muscle_mass"
            elif mes["type"] == 77:
                key = "hydration"
            elif mes["type"] == 6:
                key = "fat_ratio"
            elif mes["type"] == 88:
                key = "bone_mass"
            elif mes["type"] == 170:
                key = "visceral_fat"
            else:
                raise ValueError(f"Unknown type {mes['type']}")
            datapoint[key] = mes["value"] * (10 ** mes["unit"])

        grams = float(measure["measures"][0]["value"])
        created_timestamp = measure["created"]
        datetime_created = datetime.fromtimestamp(created_timestamp, tz)
        iso_time = datetime_created.isoformat()
        print(f"{grams/1000} KG at {datetime_created}, iso: {iso_time}")
        iso_timestamps.append(iso_time)
        datapoint["date"] = datetime_created
        withings_measures.append(datapoint)

    # pprint.pprint(withings_measures)
    
    garmin_api = init_api(GARMIN_CONNECT_EMAIL, GARMIN_CONNECT_PASSWORD)

    all_weights = garmin_api.get_weigh_ins(iso_timestamps[-1], iso_timestamps[0])
    all_already_recorded_dates = [
        x["summaryDate"] for x in all_weights["dailyWeightSummaries"]
    ]

    replace_mode = False

    for measure in withings_measures:
        if measure["date"].strftime("%Y-%m-%d") in all_already_recorded_dates:
            logger.info(f"Skipping {measure['date']} as it is already recorded")
            if replace_mode:
                logger.info(f"Deleting existing entry for {measure['date']} and re-adding...")
                garmin_api.delete_weigh_ins(measure["date"].isoformat(), delete_all=True)
            else:
                continue
        if measure["weight"] > 50 and measure["weight"] < 100:
            logger.info(f"Adding {measure['weight']} KG at {measure['date']}")

            try:
                garmin_api.add_body_composition(
                    timestamp=measure["date"].isoformat(),
                    weight=measure["weight"],
                    muscle_mass=measure["muscle_mass"],
                    percent_hydration=measure["hydration"],
                    percent_fat=measure["fat_ratio"],
                    bone_mass=measure["bone_mass"],
                    visceral_fat_rating=measure["visceral_fat"],
                )
            except KeyError:
                logger.warning("Not all body composition data available, only adding weight")
                garmin_api.add_weigh_in(
                    weight=measure["weight"],
                    timestamp=measure["date"].isoformat(),
                    unitKey="kg",
                )

            logger.info(f"Added measurement from {measure['date']}")
        else:
            # Sometimes the withings measurements seem to be way off.
            logger.warning(
                f"Skipping {measure['weight']} KG at {measure['date']} as it is not in the range of 50-100 KG"
            )

    return {
        'statusCode': 200,
        'body': 'All measurements successfully synchronized.'
    }
        


