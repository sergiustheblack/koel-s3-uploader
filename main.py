from tinytag import TinyTag
from pathlib import Path
import json, base64, imghdr, requests, logging, boto3
from os import environ as env
from urllib.parse import quote_plus



async def handler(event, context, callback=None):
    sanitize()
    session = boto3.session.Session()
    s3 = session.client(
        service_name='s3',
        endpoint_url='https://storage.yandexcloud.net'
    )
    for msg in event["messages"]:
        bucket_id = msg.get("details").get("bucket_id")
        object_id = msg.get("details").get("object_id")
        song = Path(msg.get("details").get("object_id")).name.__str__()

        if msg.get("event_metadata").get("event_type") == "yandex.cloud.events.storage.ObjectCreate":
            get_object_response = s3.get_object(Bucket=bucket_id, Key=object_id)
            with open(f"/tmp/{song}", "wb") as f:
                f.write(get_object_response['Body'].read())
            song_data = get_tags(f"/tmp/{song}")
            Path.unlink(Path(f"/tmp/{song}"), missing_ok=True)
            await handle_post(bucket_id, object_id, song_data)
        if msg.get("event_metadata").get("event_type") == "yandex.cloud.events.storage.ObjectDelete":
            await handle_delete(bucket_id, object_id)


def sanitize():
    required_env = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "KOEL_HOST",
        "KOEL_APP_KEY"
    ]
    for var in required_env:
        if not env.get(var, False):
            logging.error(f"{var} is not set")
            raise RuntimeError
    return None


def get_tags(song, meta=None):
    try:
        tag = TinyTag.get(song)
    except Exception as e:
        raise e
    image_data = tag.get_image()
    if tag.artist:
        artist = tag.artist
    elif env.get("ASSUME_TAGS", False):
        artist = Path(song).stem.split(" - ", 1)[0]
        if artist == Path(song).stem or artist.isdecimal():
            artist = "No Artist"
    if tag.title:
        title = tag.title
    elif env.get("ASSUME_TAGS", False):
        try:
            title = Path(song).stem.split(" - ", 1)[1]
        except IndexError:
            title = Path(song).stem
    try:
        lyrics = tag.extra["lyrics"]
    except KeyError:
        lyrics = ""

    koel_tags = json.loads(tag.__str__())
    koel_tags["lyrics"] = lyrics
    koel_tags["artist"] = artist
    koel_tags["title"] = title
    if image_data:
        koel_tags["cover"] = {
            "data": base64.urlsafe_b64encode(image_data).decode(),
            "extension": imghdr.what("song", h=image_data)
        }
    # Extra for compilations
    # This is not going to work until support for compilation attribute is added into Koel, sorry
    if meta and env.get("COMPILATIONS_PATH", "compilations") and env.get("COMPILATIONS_AS_ALBUMARTIST", False):
        koel_tags["albumartist"] = quote_plus(Path(meta["details"]["object_id"]).relative_to(env["COMPILATIONS_PATH"]).parent.__str__())
    return koel_tags


async def handle_delete(bucket, key):
    try:
        requests.delete(
            url=f"{env['KOEL_HOST']}/api/os/s3/song",
            data={
                "bucket":  bucket,
                "key": key,
                "appkey": env["KOEL_APP_KEY"]
            }
        )
    except Exception as e:
        raise e


async def handle_post(bucket, key, song_data):
    try:
        requests.post(
            url=f"{env['KOEL_HOST']}/api/os/s3/song",
            json={
                "bucket":  bucket,
                "key": key,
                "tags": song_data,
                "appkey": env["KOEL_APP_KEY"]
            }
        )
    except Exception as e:
        raise e
