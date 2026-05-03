"""
push_to_railway.py - Upload your local database to Railway.

Run this ONCE after your first Railway deploy to copy all your
existing customers, jobs, invoices, and history up to the live app.

Usage:
  cd data
  python push_to_railway.py <railway_url> <admin_key>

Example:
  python push_to_railway.py https://bhs-app.up.railway.app mysecretkey123
"""

import sys
import os
import requests

DB_PATH = os.path.join(os.path.dirname(__file__), 'beard_business.db')


def main():
    if len(sys.argv) < 3:
        print('Usage: python push_to_railway.py <railway_url> <admin_key>')
        print('Example: python push_to_railway.py https://bhs-app.up.railway.app mysecretkey')
        sys.exit(1)

    url = sys.argv[1].rstrip('/')
    key = sys.argv[2]

    if not os.path.exists(DB_PATH):
        print('ERROR: Database not found at ' + DB_PATH)
        sys.exit(1)

    size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    print('Uploading database (' + str(round(size_mb, 2)) + ' MB) to ' + url + ' ...')

    with open(DB_PATH, 'rb') as f:
        resp = requests.post(
            url + '/api/admin/restore-db',
            headers={'X-Admin-Key': key},
            files={'db': ('beard_business.db', f, 'application/octet-stream')},
            timeout=120
        )

    if resp.status_code == 200:
        r = resp.json()
        print('[+] Success! Railway now has ' + str(r.get('customers', '?')) + ' customers.')
        print('    Your full history is live at: ' + url)
    elif resp.status_code == 401:
        print('[!] Wrong admin key - check what you set as ADMIN_KEY in Railway.')
    else:
        print('[!] Error ' + str(resp.status_code) + ': ' + resp.text)


if __name__ == '__main__':
    main()
