#!/usr/bin/env python3

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAWCHIVE_URL = "https://pawchive.st"
PAWCHIVE_DOMAIN = urllib.parse.urlparse(PAWCHIVE_URL).netloc
WORKING_SERVICES = {"patreon", "pixiv", "fanbox"}


# --- http helpers
def build_opener(cookie_string=None, cookie_file=None):
    cj = http.cookiejar.LWPCookieJar()
    if cookie_file:
        try:
            cj.load(cookie_file, ignore_discard=True, ignore_expires=True)
        except FileNotFoundError:
            pass
    if cookie_string:
        for item in cookie_string.split(";"):
            item = item.strip()
            if "=" not in item:
                continue
            k, v = item.split("=", 1)
            ck = http.cookiejar.Cookie(
                version=0, name=k.strip(), value=v.strip(),
                port=None, port_specified=False,
                domain=PAWCHIVE_DOMAIN, domain_specified=True,
                domain_initial_dot=False, path="/", path_specified=True,
                secure=True, expires=None, discard=False,
                comment=None, comment_url=None, rest={},
                rfc2109=False,
            )
            cj.set_cookie(ck)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(),
    )
    opener.addheaders = [
        ("User-Agent", "curl/8.0"),
    ]
    return opener, cj


def request(opener, method, url, data=None, headers=None):
    h = dict(opener.addheaders)
    if data is not None and isinstance(data, dict):
        data = urllib.parse.urlencode(data).encode()
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        resp = opener.open(req, timeout=60)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# --- login
def cmd_login(args):
    opener, cj = build_opener()
    print(f"Logging in as {args.username}…", flush=True)
    status, body = request(
        opener, "POST", f"{PAWCHIVE_URL}/account/login",
        data={"username": args.username, "password": args.password, "location": ""},
    )

    has_session = any(c.name == "session" for c in cj)
    if not has_session:
        print("Login failed: no session cookie received.")
        return 1

    # Verify the session works by calling an authenticated endpoint
    check_status, _ = request(
        opener, "GET", f"{PAWCHIVE_URL}/api/v1/account/favorites?type=artist",
    )
    if check_status in (302, 401):
        print("Login failed: incorrect username or password.")
        return 1

    save_path = args.output if args.output else args.cookie_file
    cj.save(save_path, ignore_discard=True, ignore_expires=True)
    print(f"Logged in. Session cookie saved to {save_path}")
    return 0


# --- list
def cmd_list(args):
    opener, cj = build_opener(cookie_string=args.cookie, cookie_file=args.cookie_file)
    status, body = request(
        opener, "GET", f"{PAWCHIVE_URL}/api/v1/account/favorites?type=artist",
    )
    if status in (302, 401):
        print("Not authenticated. Login first or provide a session cookie.")
        return 1
    if status != 200:
        print(f"Error: HTTP {status}")
        return 1

    favs = json.loads(body)
    if not favs:
        print("No favorites found.")
        return 0

    print(f"Found {len(favs)} favorited creators on pawchive:")
    for f in favs:
        print(f"  {f['service']:12s} {f['id']:12s}  {f.get('name', '?')}")
    return 0


# --- import
def cmd_import(args):
    opener, cj = build_opener(cookie_string=args.cookie, cookie_file=args.cookie_file)

    # load json
    with open(args.json_file, "r") as f:
        data = json.load(f)

    artists = data.get("artists", []) if isinstance(data, dict) else data
    if not isinstance(artists, list):
        print("JSON must contain an 'artists' list.")
        return 1

    # build target list
    only_working = (args.service == "working")
    targets = []
    skipped = 0
    for artist in artists:
        try:
            service = (artist.get("service") or "").strip().lower()
            aid = artist.get("id")
            if not service or aid is None:
                skipped += 1
                continue
            if only_working and service not in WORKING_SERVICES:
                skipped += 1
                continue
            targets.append((service, str(aid), artist.get("name", "?")))
        except Exception:
            skipped += 1

    print(f"Loaded {len(targets)} target(s) from JSON. Skipped {skipped}.")

    if not targets:
        return 0

    # auth and optionally fetch existing favorites
    existing = set()
    if not args.force:
        status, body = request(
            opener, "GET", f"{PAWCHIVE_URL}/api/v1/account/favorites?type=artist",
        )
        if status in (302, 401):
            print("Not authenticated. Run 'login' first or pass --cookie.")
            return 1
        if status == 200:
            try:
                for f in json.loads(body):
                    existing.add((f["service"], f["id"]))
            except Exception:
                pass
            if existing:
                print(f"Found {len(existing)} already-favorited creators on pawchive.")

    # favorite each
    fav_count, skip_count, error_count = 0, 0, 0
    errors = []
    total = len(targets)

    for i, (service, cid, name) in enumerate(targets, 1):
        if existing and (service, cid) in existing:
            print(f"[{i}/{total}] ⏭  Already favorited: {service}/{cid} ({name})")
            skip_count += 1
            continue

        status, body = request(
            opener, "POST",
            f"{PAWCHIVE_URL}/api/v1/favorites/creator/{service}/{cid}",
        )
        if status in (302, 401):
            errors.append(f"{service}/{cid} ({name}) -> not authenticated")
            error_count += 1
            print(f"[{i}/{total}] ❌ Not authenticated at {service}/{cid}")
            break
        elif status in (200, 204):
            fav_count += 1
            print(f"[{i}/{total}] ★ Favorited: {service}/{cid} ({name})")
        else:
            errors.append(f"{service}/{cid} ({name}) -> HTTP {status}")
            error_count += 1
            print(f"[{i}/{total}] ❌ Error (HTTP {status}): {service}/{cid} ({name})")

        # polite delay
        if i < total:
            time.sleep(0.5)

    # summary
    print(f"\nDone: {fav_count} favorited, {skip_count} skipped, {error_count} errors")
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  ❌ {e}")

    return 1 if error_count else 0


# --- CLI
def main():
    parser = argparse.ArgumentParser(
        description="Import kemono favorites to pawchive",
    )
    parser.add_argument("--cookie", help="Session cookie value (e.g. 'session=abc123')")
    parser.add_argument(
        "--cookie-file",
        default=os.path.join(SCRIPT_DIR, ".pawchive_cookies.txt"),
        help="Cookie jar file (default: .pawchive_cookies.txt in script dir)",
    )

    sub = parser.add_subparsers(dest="command")

    # login
    login_p = sub.add_parser("login", help="Login to pawchive and save session")
    login_p.add_argument("username")
    login_p.add_argument("password")
    login_p.add_argument(
        "--output",
        help="Save session cookie to this path",
    )

    # list
    list_p = sub.add_parser("list", help="List current pawchive favorites")

    # import
    import_p = sub.add_parser("import", help="Import favorites from kemono JSON export")
    import_p.add_argument("json_file", help="Kemono favorites export JSON file")
    import_p.add_argument(
        "--service", choices=("working", "all"), default="working",
        help="Filter: 'working' (patreon/pixiv/fanbox) or 'all' (default: working)",
    )
    import_p.add_argument(
        "--force", action="store_true",
        help="Skip duplicate check and re-favorite all",
    )

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "login":
        return cmd_login(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "import":
        return cmd_import(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
