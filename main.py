from tinytag import TinyTag
from pathlib import Path
import json, base64, imghdr, requests, logging, boto3
from os import environ as env
from urllib.parse import quote_plus

if env.get("TELEGRAM_CHAT") and env.get("TELEGRAM_TOKEN"):
    import telegram
    from telegram.parsemode import ParseMode

class S3Song(object):
    def __init__(self, s3_bucket, s3_object, s3_endpoint, action):
        self.s3_bucket = s3_bucket
        self.s3_object = s3_object
        self.s3_endpoint = s3_endpoint
        # create or delete
        self.action = action

        self.file_name = str(Path(self.s3_object).name)
        self.file_path = f"/tmp/{self.file_name}"

    def __str__(self):
        return str(vars(self))


async def handler(song: S3Song):
    try:
        sanitize_env()
        sanitize_file(song)
        loglevel = env.get('LOGLEVEL', 'WARNING').upper()
        logging.getLogger().setLevel(logging.getLevelName(loglevel))

        session = boto3.session.Session()
        s3 = session.client(
            service_name='s3',
            endpoint_url=song.s3_endpoint
        )

        if song.action == "create":
            get_object_response = s3.get_object(Bucket=song.s3_bucket, Key=song.s3_object)
            with open(song.file_path, "wb") as f:
                f.write(get_object_response['Body'].read())
            song_data = get_tags(song)
            Path.unlink(Path(song.file_path), missing_ok=True)
            await handle_post(song.s3_bucket, song.s3_object, song_data)
        if song.action == "delete":
            await handle_delete(song.s3_bucket, song.s3_object)
    except Exception as e:
        if env.get("TELEGRAM_CHAT") and env.get("TELEGRAM_TOKEN"):
            telegram_send_error(f"Error handling {song.s3_object}\n{e}")
            raise e
        else:
            raise e


def sanitize_env():
    required_env = [
        "KOEL_HOST",
        "KOEL_APP_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY"
    ]

    for var in required_env:
        if not env.get(var):
            logging.error(f"{var} is not set")
            raise RuntimeError(f"{var} is not set")

    if env.get("ASSUME_COMPILATIONS") and env.get("REMOVE_ALBUMARTIST_TAG"):
        raise RuntimeError("Variables ASSUME_COMPILATIONS and REMOVE_ALBUMARTIST_TAG are mutually exclusive")
    return None


def sanitize_file(song: S3Song):
    supported_ext = [
        "mp3",
        "ogg",
        "m4a",
        "flac"
    ]
    if Path(song.s3_object).suffix.lstrip(".").lower() not in supported_ext:
        logging.warning(f"File {song.file_name} is unsupported. Skipping")
        Path.unlink(Path(song.file_path), missing_ok=True)
        raise SystemExit(f"File {song.file_name} is unsupported. Skipping")
    return None


def get_tags(song: S3Song):
    try:
        tag = TinyTag.get(song.file_path, image=True)
    except Exception as e:
        logging.error("Error getting tags")
        raise RuntimeError(f"Error getting tags: {e}")
    image_data = tag.get_image()
    koel_tags = json.loads(str(tag))

    try:
        koel_tags["lyrics"] = tag.extra["lyrics"]
    except KeyError:
        koel_tags["lyrics"] = ""

    if image_data:
        koel_tags["cover"] = {
            "data": base64.b64encode(image_data).decode(),
            "extension": imghdr.what("song", h=image_data)
        }

    if env.get("REMOVE_ALBUMARTIST_TAG"):
        koel_tags.pop("albumartist", None)

    if env.get("ASSUME_TAGS") and env.get("ASSUME_TAGS_FORCE"):
        logging.info(f"Assuming tags for {song.s3_object}")
        koel_tags = assume_tags(song, koel_tags, True)
        logging.info(f"Assuming tags for {song.s3_object}")
    elif env.get("ASSUME_TAGS") and not (koel_tags["artist"] and koel_tags["album"] and koel_tags["title"]):
        logging.info(f"Assuming tags for {song.s3_object}")
        koel_tags = assume_tags(song, koel_tags, False)
        logging.debug(f"Tags assumed: {koel_tags}")

    return koel_tags


def assume_tags(song: S3Song, tags, force = False):
    def general():
        """
            Only filenames. For files like:
            Artist Name - Song Name.mp3
        :return: {title: "Song Name", artist: "Artist Name", album: ""}
        """
        ret = {"album": "", "track": ""}  # we don't have any info about album and track in this case

        artist = song.file_name.split(" - ", 1)[0]
        if artist == song.file_name or artist.isdecimal():
            artist = "No Artist"
        ret["artist"] = artist

        try:
            ret["title"] = Path(song.file_name).stem.split(" - ", 1)[1]
        except IndexError:
            try:
                if Path(song.file_name).stem.split(".", 1)[0].lstrip().isdecimal():
                    ret["title"] = Path(song.file_name).stem.split(".", 1)[1].lstrip()
                else:
                    ret["title"] = Path(song.file_name).stem
            except IndexError:
                ret["title"] = Path(song.file_name).stem
        # Extra for compilations
        # This is not going to work until support for compilation attribute is added into Koel, sorry
        if env.get("ASSUME_COMPILATIONS"):
            ret[env.get("ASSUME_COMPILATIONS_TAG", "albumartist")] = quote_plus(
                str(Path(song.s3_object).relative_to(env.get("COMPILATIONS_PATH", "compilations")).parent))
        return ret

    def by_album(root):
        """
            For files in discographies. Path should be
            ALBUMS_PATH/Artist Name/Album Name/Song Name.mp3
            or
            ALBUMS_PATH/Artist Name/2000 - Album Name/01. Song Name.mp3
            or
            ALBUMS_PATH/Artist Name/demos/Album Name/01. Song Name.mp3
            or combination of these
            if ASSUME_ADD_YEAR is set, then year is added to album name
        :return: {title: "Song Name", artist: "Artist Name", album: "Album Name"}
        """
        pathparts = Path(song.s3_object).relative_to(root).parts
        ret = {"artist": pathparts[0]}
        if pathparts[-2].split(" - ", 1)[0].isdecimal():
            year_in_album = True
            year_separator = " - "
        elif pathparts[-2].split(".", 1)[0].isdecimal():
            year_in_album = True
            year_separator = "."
        else:
            year_in_album = False

        if year_in_album:
            if env.get("ASSUME_ADD_ALBUM_YEAR"):
                ret["album"] = pathparts[-2]
            else:
                ret["album"] = pathparts[-2].split(year_separator, 1)[1].lstrip()
        else:
            ret["album"] = pathparts[-2]

        if pathparts[-1].split(".", 1)[0].isdecimal():
            ret["title"] = Path(pathparts[-1]).stem.split(".", 1)[1].lstrip()
            ret['track'] = Path(pathparts[-1]).stem.split(".", 1)[0]
        elif pathparts[-1].split(" - ", 1)[0].isdecimal():
            ret["title"] = Path(pathparts[-1]).stem.split(" - ", 1)[1]
            ret['track'] = Path(pathparts[-1]).stem.split(" - ", 1)[0]
        else:
            ret["title"] = Path(pathparts[-1]).stem
            ret["track"] = ""
        return ret
    pth = env.get("ALBUMS_PATH", "albums")
    if pth and song.s3_object.startswith(pth):
        logging.debug("Assuming tags based on ALBUMS_PATH")
        try:
            assumed = by_album(pth)
        except Exception as e:
            logging.debug(e)
            logging.debug("Assuming by ALBUMS_PATH failed. Falling back to general assuming")
            assumed = general()
    else:
        logging.debug("General assuming")
        assumed = general()
    for tag in ["title", "album", "artist", "track"]:
        if assumed.get(tag) and force:
            tags[tag] = assumed[tag]
        elif not tags.get(tag):
            tags[tag] = assumed[tag]
    return tags


async def handle_delete(bucket, key):
    response = requests.delete(
        url=f"{env['KOEL_HOST']}/api/os/s3/song",
        data={
            "bucket":  bucket,
            "key": key,
            "appKey": env["KOEL_APP_KEY"]
        }
    )
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logging.error(e)
        raise e


async def handle_post(bucket, key, song_data):
    response = requests.post(
        url=f"{env['KOEL_HOST']}/api/os/s3/song",
        json={
            "bucket":  bucket,
            "key": key,
            "tags": song_data,
            "appKey": env["KOEL_APP_KEY"]
        }
    )
    logging.debug(response.request.body)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logging.error(e)
        raise e


def telegram_send_error(text):
    bot = telegram.Bot(env.get("TELEGRAM_TOKEN"))
    parse_mode = ParseMode.HTML
    text = f"\u2757Error upload to Koel:\n{text}"
    try:
        bot.send_message(env.get("TELEGRAM_CHAT"), text, parse_mode=parse_mode)
    except Exception as e:
        logging.error(f'Error sending message via Telegram: {e}')
        pass


def event(event, context=None, callback=None):
    """
        Returns the event from s3 trigger
    """
    logging.getLogger().setLevel(logging.INFO)
    logging.info(json.dumps(event))
    return {
        'statusCode': 200,
        'body': json.dumps({
            'event': event,
        }),
    }


async def sync(s3_bucket: str = None,  s3_path: str = "", s3_endpoint: str = None):
    """
        Uploads songs from s3 bucket to Koel
    :param s3_endpoint:
    :param s3_bucket:
    :param s3_path:
    :return:
    """
    try:
        # Since we can call this locally, sanitize arguments.
        # Environment takes precedence over function args ¯\_(ツ)_/¯
        s3_endpoint = env.get("SYNC_ENDPOINT", s3_endpoint)
        s3_bucket = env.get("SYNC_BUCKET", s3_bucket)
        s3_path = env.get("SYNC_PATH", s3_path)
        if not s3_endpoint:
            raise RuntimeError("s3 endpoint not set")
        if not s3_bucket:
            raise RuntimeError("s3 bucket not set")

        sanitize_env()
        loglevel = env.get('LOGLEVEL', 'WARNING').upper()
        logging.getLogger().setLevel(logging.getLevelName(loglevel))
        session = boto3.session.Session()
        s3 = session.client(
            service_name='s3',
            endpoint_url=s3_endpoint
        )
        files = s3.list_objects_v2(Bucket=s3_bucket, Prefix=s3_path)
        for file in files.get("Contents", []):
            if file.get("Size", 0) > 0:
                song = S3Song(
                    s3_bucket,
                    file["Key"],
                    s3_endpoint,
                    "create"
                )
                logging.info(f"Syncing song {song.s3_object}")
                try:
                    sanitize_file(song)
                except SystemExit:
                    continue
                get_object_response = s3.get_object(Bucket=song.s3_bucket, Key=song.s3_object)
                with open(song.file_path, "wb") as f:
                    f.write(get_object_response['Body'].read())
                song_data = get_tags(song)
                Path.unlink(Path(song.file_path), missing_ok=True)
                await handle_post(song.s3_bucket, song.s3_object, song_data)
    except Exception as e:
        if env.get("TELEGRAM_CHAT") and env.get("TELEGRAM_TOKEN"):
            telegram_send_error(f"Error handling {song.s3_object} during sync\n{e}")
            raise e
        else:
            raise e
