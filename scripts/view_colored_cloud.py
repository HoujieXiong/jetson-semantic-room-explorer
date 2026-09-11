"""Open a trusted local map in a dedicated Chromium software-WebGL window."""

import argparse
import os
from pathlib import Path


def browser_command(html):
    html = html.resolve(strict=True)
    if not html.is_file() or html.suffix.lower() != '.html':
        raise ValueError('Expected a local map HTML file')
    return [
        '/snap/bin/chromium',
        '--user-data-dir='+str(Path.home()/'snap/chromium/common/room-cloud-viewer'),
        '--no-first-run', '--no-default-browser-check', '--disable-sync',
        '--disable-background-networking', '--disable-component-update',
        '--disable-background-mode', '--window-size=1440,1000',
        # The Jetson's default browser did not provide a usable WebGL context.
        # Keep this opt-in software renderer confined to the local map profile.
        '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
        '--app='+html.as_uri(),
    ]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    args = parser.parse_args()
    try:
        command = browser_command(args.html)
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))
    os.execv(command[0], command)
