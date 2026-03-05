import os.path
from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def main():
    creds = None
    
    if not os.path.exists('credentials.json'):
        print("ERROR: credentials.json not found.")
        return

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        # We must disable open_browser and use a fixed port so we can curl the callback
        creds = flow.run_local_server(port=54321, open_browser=False)
    except Exception as e:
        print(f"Failed during authentication flow: {e}")
        return

    if creds:
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
        print("\n--- COPY BELOW THIS LINE ---")
        print(creds.to_json())
        print("--- COPY ABOVE THIS LINE ---\n")

if __name__ == '__main__':
    main()
