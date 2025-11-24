#!/usr/bin/env python3
"""Utility to generate a Werkzeug password hash for the ADMIN_PASSWORD_HASH env var.

Usage:
  python scripts/make_admin_hash.py
  python scripts/make_admin_hash.py --password 'MySecret123'

The script prints a hash you can copy into your `.env` as:
  ADMIN_PASSWORD_HASH=<the-hash>
"""
import argparse
import getpass
from werkzeug.security import generate_password_hash


def main():
    parser = argparse.ArgumentParser(description='Generate ADMIN_PASSWORD_HASH for Smart Help Desk')
    parser.add_argument('--password', '-p', help='Plain-text password (optional)')
    parser.add_argument('--method', '-m', default='pbkdf2:sha256:260000', help='Hash method (Werkzeug style)')
    args = parser.parse_args()

    if args.password:
        pwd = args.password
    else:
        pwd = getpass.getpass('Enter admin password: ')
        pwd2 = getpass.getpass('Confirm password: ')
        if pwd != pwd2:
            print('Passwords do not match. Aborting.')
            raise SystemExit(1)

    h = generate_password_hash(pwd, method=args.method)
    print('\nCopy this value into your .env as:')
    print('\nADMIN_PASSWORD_HASH=' + h + '\n')


if __name__ == '__main__':
    main()
