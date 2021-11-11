from tinytag import TinyTag
from pathlib import Path
import json, base64, imghdr


def get_tags(song):
    try:
        tag = TinyTag.get(song)
    except Exception as e:
        raise e
    image_data = tag.get_image()
    if tag.artist:
        artist = tag.artist
    else:
        artist = Path(song).stem.split(" - ", 1)[0]
        if artist == Path(song).stem or artist.isdecimal():
            artist = "No Artist"
    if tag.title:
        title = tag.title
    else:
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
    return koel_tags


async def handler(e, context, callback):
    pass
