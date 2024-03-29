# telegram-auto-collect

A Telegram Daemon (not a bot) for forward ,collect, record automation 

This daemon is based on [telegram-download-daemon project from alfem](https://github.com/alfem/telegram-download-daemon).

This tool can help you:

* auto queue download downloadable media you want (with auto dedupe)
* auto forward every possible document in a group or channel
* get everything from a group or channel
* record every message information in a group or channel

Telegram bots are limited to 20Mb file size downloads. So I wrote this agent
or daemon to allow bigger downloads (limited to 2GB by Telegram APIs).

# Installation
The installation has three part:
### SQL
You will need MSSQL(express version is fine but more complicate setting)

Use the [SQL-TGrobot-build.sql](https://github.com/B3N50N/TG-auto-collect/blob/main/SQL-TGrobot-build.sql) to deploy the sql database

### config file
You will need to modify all possible field in [TG_auto_save.json]

include:

* sql connection string
* mirror channel (channel id)

both are required


### python
You need Python3 (3.6 works fine, 3.5 will crash randomly).

Install dependencies by running this command:

    pip venv TG-auto

    source ./TG-auto/bin/activate

    pip install -r requirements.txt

(If you don't want to install `cryptg` and its dependencies, you just need to install `telethon`)

Warning: If you get a `File size too large message`, check the version of Telethon library you are using. Old versions have got a 1.5Gb file size limit.


Obtain your own api id: https://core.telegram.org/api/obtaining_api_id

# Usage

You need to configure these values:

| Environment Variable     | Command Line argument | Description                                                  | Default Value       |
|--------------------------|:-----------------------:|--------------------------------------------------------------|---------------------|
| `TELEGRAM_DAEMON_API_ID`   | `--api-id`              | api_id from https://core.telegram.org/api/obtaining_api_id   |                     |
| `TELEGRAM_DAEMON_API_HASH` | `--api-hash`            | api_hash from https://core.telegram.org/api/obtaining_api_id |                     |
| `TELEGRAM_DAEMON_DEST`     | `--dest`                | Destination path for downloaded files                       | `/telegram-downloads` |
| `TELEGRAM_DAEMON_TEMP`     | `--temp`                | Destination path for temporary (download in progress) files                       | `/telegram-downloads-temp` |
| `TELEGRAM_DAEMON_CHANNEL`  | `--channel`             | A channel to read all your command and Download document|                     |

You can define them as Environment Variables, or put them as a command line arguments, for example:

    python telegram-download-daemon.py --api-id <your-id> --api-hash <your-hash> --channel <channel-number>


If it ask you to login with your phone, verification code, password, just login 

after that you'll see config load, sql load

Next

If you want to queue download something from telegram, just forward downloadable media to the `TELEGRAM_DAEMON_CHANNEL`

For other function you'll have to "talk" with this daemon using your Telegram client:


* this part of document is not yet born

# Note
You can have this tool to do anything you want even provide service to other except:

'Selling it'

Or i will stop update this repository and make it private

(You can't berak the GNU GPL V3 license ,since part of code of this project is based on [alfem](https://github.com/alfem/telegram-download-daemon/blob/master/LICENSE.txt))

Also I need help to finish this document and make this tool better.

Ofcource, feel free to give me any suggestion 


