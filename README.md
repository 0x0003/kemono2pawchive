A small python script that batch imports exported kemono favorites into pawchive.  
Zero external dependencies, only python stdlib.

For GUI, try [LeoIsamaru/Pawchive-Favorites-Importer-from-kemono](https://github.com/LeoIsamaru/Pawchive-Favorites-Importer-from-kemono), it was used as a reference for this project.

## Obtaining kemono favorites

Open [export favorites page](https://kemono.cr/account/favorites/export) in your browser, click export, copy, paste into a file (named `favorites.json` for usage examples).

## Usage

```bash
# login (saves session to .pawchive_cookies.txt in the script directory,
# use `--output` to override)
#
# NOTE: run in a private shell session to avoid saving credentials to history,
#       or clean shell history manually afterwards
python3 kemono2pawchive.py login "username" "password"

# list current pawchive favorites
python3 kemono2pawchive.py list

# import from kemono favorites JSON export, only working services (script line 14)
python3 kemono2pawchive.py import favorites.json

# import with all services and skip duplication checks
python3 kemono2pawchive.py import favorites.json --service all --force

# pass session cookie value directly (skip login)
python3 kemono2pawchive.py --cookie "session=abc123" import favorites.json

# override cookie file (default is ".pawchive_cookies.txt" in script directory)
python3 kemono2pawchive.py --cookie-file "/path/to/cookies.txt" import favorites.json
```

