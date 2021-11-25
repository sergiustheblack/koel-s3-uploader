import main
import json, logging


async def handler(event, context=None, callback=None):
    for msg in event["messages"]:
        if msg.get("event_metadata").get("event_type") == "yandex.cloud.events.storage.ObjectCreate":
            action = "create"
        elif msg.get("event_metadata").get("event_type") == "yandex.cloud.events.storage.ObjectDelete":
            action = "delete"
        else:
            logging.error("Unknown s3 operation")
            raise RuntimeError
        song = main.S3Song(
            msg.get("details").get("bucket_id"),
            msg.get("details").get("object_id"),
            "https://storage.yandexcloud.net",
            action
        )
        await main.handler(song)


async def sync(s3_bucket: str = None,  s3_path: str = ""):
    await main.sync(s3_bucket=s3_bucket, s3_path=s3_path, s3_endpoint="https://storage.yandexcloud.net")
