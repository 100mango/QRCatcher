#!/usr/bin/env python3
"""Verify the checked-in iPad icons; archives have no hidden generation step."""
from pathlib import Path
from verify_ios_icons import source_icons

if __name__ == '__main__':
    result=source_icons(Path(__file__).resolve().parents[1])
    for row in result['declared_images']:
        if row['idiom']=='ipad':print(row['filename'],row['width'])
