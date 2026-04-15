#!/usr/bin/env python3
"""
Telethon Session String Generator
==================================
Run this script ONCE on your local machine to generate a session string
for use in GitHub Actions CI/CD (as TG_SESSION_STRING secret).

Prerequisites:
  1. Go to https://my.telegram.org and create an application.
  2. Note your api_id (integer) and api_hash (string).
  3. pip install telethon

Usage:
  python generate_tg_session.py

It will ask for your phone number and a verification code from Telegram.
The output session string should be stored as the TG_SESSION_STRING
GitHub repository secret.
"""

import sys

try:
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
except ImportError:
    print("ERROR: telethon is not installed. Run: pip install telethon")
    sys.exit(1)


def main():
    print("=" * 60)
    print("Telethon Session String Generator for CI/CD")
    print("=" * 60)
    print()

    api_id = input("Enter your Telegram API ID (integer): ").strip()
    api_hash = input("Enter your Telegram API Hash (string): ").strip()

    if not api_id or not api_hash:
        print("ERROR: Both API ID and API Hash are required.")
        sys.exit(1)

    try:
        api_id = int(api_id)
    except ValueError:
        print("ERROR: API ID must be an integer.")
        sys.exit(1)

    print()
    print("Starting Telethon client... You will be asked to enter your phone number and OTP.")
    print()

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()

    print()
    print("=" * 60)
    print("SUCCESS! Your session string is below.")
    print("Copy this ENTIRE string and save it as TG_SESSION_STRING")
    print("in your GitHub repository secrets.")
    print("=" * 60)
    print()
    print(session_string)
    print()
    print(f"Length: {len(session_string)} chars")
    print()
    print("SECURITY WARNING: This session string gives full access to")
    print("your Telegram account. Keep it secret. Never commit it to git.")


if __name__ == "__main__":
    main()
