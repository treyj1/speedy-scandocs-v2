#!/bin/bash
# Starts Speedy Scandocs from this folder on a Mac. Double-click it in Finder.
# The first time, it installs the Python libraries the app needs into a .venv folder here.
# Most people should use the packaged app from the releases page instead.

cd "$(dirname "$0")" || exit 1

tell() {
    osascript -e "display alert \"Speedy Scandocs\" message \"$1\" as warning" >/dev/null
}

python=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        python="$candidate"
        break
    fi
done

if [ -z "$python" ]; then
    tell "Python isn't installed. Install Python 3.11 or newer from python.org, then open Speedy Scandocs again."
    exit 1
fi

if ! .venv/bin/python check_setup.py 2>/dev/null; then
    echo "Speedy Scandocs needs to install a few things the first time. This takes a minute or two."
    "$python" -m venv .venv &&
        .venv/bin/python -m pip install -r requirements.txt
    if ! .venv/bin/python check_setup.py 2>/dev/null; then
        tell "The install didn't finish. Check the internet connection and try again."
        exit 1
    fi
fi

exec .venv/bin/python app.py "$@"
