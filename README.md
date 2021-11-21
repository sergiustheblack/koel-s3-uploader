# Koel s3 uploader

Initially made for use with Yandex Cloud Object Storage and [Koel](https://koel.dev)

### Pros
* Can automatically populate song tags based on filename (if tags are not present)
* Easy to extend to other s3 platforms
### Cons
* Not tested with AWS currently
* Usage with Yandex cloud requires modifying Koel's aws config (Koel v5.1.8)
## Fast start
1) Download archive from GitHub as zip. Extract it and repack so only repo files exist in the archive (without parent folder)
   bash oneliner: `d=$(unzip ./koel-s3-uploader-yandex.zip 2>&1 | grep creating | awk '{print $NF}') && zip
 -j s3.zip $d/*.py`
3) Create private s3 bucket, lambda-like function, trigger and service user
   * Yandex
      1) [Bucket](https://cloud.yandex.ru/docs/storage/operations/buckets/create)
      2) [Cloud function](https://cloud.yandex.ru/docs/functions/operations/function/function-create)
      3) [Trigger, User](https://cloud.yandex.ru/docs/functions/concepts/trigger/os-trigger)
   * AWS
       1) [Official Koel docs for AWS](https://docs.koel.dev/aws-s3.html)
       2) [Bucket](https://docs.aws.amazon.com/AmazonS3/latest/userguide/create-bucket-overview.html)
       3) [Lambda](https://docs.aws.amazon.com/lambda/latest/dg/getting-started-create-function.html)
       4) [Trigger](https://docs.aws.amazon.com/lambda/latest/dg/with-s3-example.html)
4) When creating cloud function, upload archive from step 1 into it.
5) Set up at least required environment variables in function settings. Checkout section below.
6) Select entrypoint for cloud function:
   * AWS: aws.handler
   * Yandex: yandex.handler
## Environment variable reference
| Variable                   | Default or required | Example            | Description |
| ---                        | ---                 | ---                | ---         |
| KOEL_HOST                  | Required            | https://koel.dev   | Public url of your Koel server. |
| KOEL_APP_KEY               | Required            | base64:abcdef=     | Value from APP_KEY in .env |
| AWS_ACCESS_KEY_ID          | Required            | abc123abc...       | Service User's secret key ID |
| AWS_SECRET_ACCESS_KEY      | Required            | AbC1a123...        | Service User's secret key |
| LOGLEVEL                   | WARNING             | DEBUG              | Logging level upon function invocation |
| ASSUME_TAGS                | False               | True               | Assuming: Try to create missing tags (see ref below) |
| ALBUMS_PATH                | albums              | artists            | Assuming: Root folder of your discographies | 
| ASSUME_ADD_ALBUM_YEAR      | False               | True               | Assuming: If album folder contains year, add to album name | 
| ~~ASSUME_COMPILATIONS~~    | ~~False~~           | ~~True~~           | Not supported by Koel: add tag with name of your compilation based on path |  
| ~~COMPILATIONS_PATH~~      | ~~compilations~~    | ~~my-awseme-lib~~  | Not supported by Koel: root path of your compilations |
| ~~ASSUME_COMPILATIONS_TAG~~| ~~albumartist~~     | ~~compilation~~    | Not supported by Koel: tag to assign compilation name to |
## Important: usage of non-AWS s3
As for Koel v5.1.8, to use Koel with non-AWS Object Storage, you have to modify config/aws.php in the project.
Add `'endpoint' => env('AWS_ENDPOINT', 'https://s3.amazonaws.com'),` to it and set up `AWS_ENDPOINT` at `.env` of your Koel installation.
Info about entrypoint should be provided by your cloud provider. You might be required to use docker bind mount for this file.

## Advanced features
### Assuming
Assuming is pupulation of missing tags in records. It never rewrites any existing tags, but trying to assume if they miss.
Currently supported tags are _Title_, _Artist_, _Album_, _Track_. To enable this feature, set ASSUME_TAGS environment variable to True.

  This is how it works:
   create folder for your discographies (default is _albums_), and put everything into structure:
  `albums/Artist/[anything]/Album/song.mp3`

Examples:

| Path                                           | additional environment               | tags
| ---                                            | ---                       | --- 
| albums/Dope/Group Therapy/01. Falling Away.mp3 |  | Title: Falling Away, Album: Group Therapy, Artist: Dope, Track: 01 |
| albums/Dope/Group Therapy/01 - Falling Away.mp3 |  | Title: Falling Away, Album: Group Therapy, Artist: Dope, Track: 01 |
| my/Dope/albums/Group Therapy/Falling Away.mp3 | ALBUMS_PATH=my | Title: Falling Away, Album: Group Therapy, Artist: Dope |
| albums/Dope/albums/2003 - Group Therapy/Falling Away.mp3 |  | Title: Falling Away, Album: Group Therapy, Artist: Dope |
| albums/Dope/albums/2003 - Group Therapy/Falling Away.flac | ASSUME_ADD_ALBUM_YEAR=True  | Title: Falling Away, Album: 2003 - Group Therapy, Artist: Dope |
| Dope/albums/2003 - Group Therapy/03. Falling Away.mp3 | | Title: Falling Away, Artist: No Artist |

However, this behaviour might be buggy and turned off by default.
### Telegram notifications
You can send notifications about failed uploads to Telegram.
To use it, first uncomment `python-telegram-bot` in `requirements.txt` before upload,
create Telegram bot via BotFather and assign `TELEGRAM_CHAT` and `TELEGRAM_TOKEN` environment variables in lambda.
## Development
Potentially this app can work with any s3 provider which supports s3 triggers and lambda-like functions.
But we need to determine event structure passed by trigger.
To understand it, you can call `main.event` function from inside lambda, it will dump raw event.

Then add file with clear platform definition, for example `oracle.py` and create function `handler` inside.
Put the code needed for parsing and setting required data (object path, bucket name and s3 entrypoint) into `handler`,
construct object of class `main.S3Song` and call `await main.handler(song)` at the end. Simple. For example see `yandex.py`
