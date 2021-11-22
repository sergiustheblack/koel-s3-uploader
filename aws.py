import main
import json, logging


async def handler(event, context=None, callback=None):
    for msg in event["Records"]:
        if msg.get("eventName") == "ObjectCreated:Put" or msg.get("eventName") == "ObjectCreated:CompleteMultipartUpload":
            action = "create"
        elif msg.get("eventName") == "ObjectRemoved:Delete" or msg.get("eventName") == "ObjectRemoved:DeleteMarkerCreated":
            action = "delete"
        else:
            logging.error("Unknown s3 operation")
            raise RuntimeError
        song = main.S3Song(
            msg.get("s3").get("bucket").get("name"),
            msg.get("s3").get("object").get("key"),
            "https://s3.amazonaws.com",
            action
        )
        await main.handler(song)


async def sync(s3_bucket: str, s3_path: str = ""):
    await main.sync(s3_bucket, "https://s3.amazonaws.com", s3_path)
