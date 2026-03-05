import json
import requests

def exchange_code():
    with open("credentials.json", "r") as f:
        creds = json.load(f)["installed"]
        
    code = "4/0AfrIepAANSXMsAL6q2M2E5GKybEW_D7a9YgAmSYQTVLLJ1-y6XWxM-tisZPJ1-ZlWOJgrg"
    
    data = {
        "code": code,
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "redirect_uri": "http://localhost",
        "grant_type": "authorization_code"
    }
    
    response = requests.post(creds["token_uri"], data=data)
    token_data = response.json()
    
    if "error" in token_data:
        print(f"Error exchanging code: {token_data}")
        return
        
    final_creds = {
        "token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "token_uri": creds["token_uri"],
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "scopes": ["https://www.googleapis.com/auth/drive.file"],
        "expiry": "2030-01-01T00:00:00.000000Z" # Dummy far future, google-auth refreshes anyway
    }
    
    with open("token.json", "w") as f:
        json.dump(final_creds, f, indent=4)
        
    print("\n✅ SUCCESS! Google OAuth 2.0 Token Generated.")
    print("--- RAW JSON (COPY EVERYTHING BELOW) ---")
    print(json.dumps(final_creds, indent=2))
    print("--- COPY ABOVE THIS LINE ---\n")

if __name__ == "__main__":
    exchange_code()
