"""
One-time OAuth flow to get refresh_token for Mikhail's Google Drive.
This token allows the bot to create new Google Sheets files in Mikhail's Drive.

Usage:
  1. Run this script: python3 get_oauth_token.py
  2. Open the printed URL in Chrome
  3. Approve the access
  4. After redirect (which will fail to load), copy the full URL from the address bar
  5. Paste it here when prompted
"""
import os
import re
import json
import urllib.parse
import urllib.request
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
REDIRECT_URI = "http://localhost"
SCOPES = "https://www.googleapis.com/auth/drive.file"

# Step 1: Build auth URL
params = {
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": SCOPES,
    "access_type": "offline",
    "prompt": "consent",
}
auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

print("\n" + "="*60)
print("STEP 1: Open this URL in Chrome:")
print("="*60)
print(auth_url)
print("="*60)
print("\nAfter approving, Chrome will redirect to http://localhost?code=...")
print("The page will fail to load — that's OK.")
print("Copy the FULL URL from the browser address bar and paste it below.\n")

redirect_url = input("Paste the full redirect URL here: ").strip()

# Step 2: Extract code from redirect URL
code_match = re.search(r'[?&]code=([^&]+)', redirect_url)
if not code_match:
    print("ERROR: No code found in URL:", redirect_url)
    exit(1)

code = urllib.parse.unquote(code_match.group(1))
print(f"\nExtracted code: {code[:20]}...")

# Step 3: Exchange code for tokens
token_data = urllib.parse.urlencode({
    "code": code,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
}).encode()

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=token_data,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    method="POST"
)

with urllib.request.urlopen(req) as resp:
    tokens = json.loads(resp.read())

refresh_token = tokens.get("refresh_token")
if not refresh_token:
    print("ERROR: No refresh_token in response:", tokens)
    exit(1)

print(f"\nRefresh token obtained: {refresh_token[:20]}...")

# Step 4: Save to .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
with open(env_path) as f:
    env_content = f.read()

if "GOOGLE_OAUTH_REFRESH_TOKEN=" in env_content:
    env_content = re.sub(r'GOOGLE_OAUTH_REFRESH_TOKEN=.*', f'GOOGLE_OAUTH_REFRESH_TOKEN={refresh_token}', env_content)
else:
    env_content += f"\nGOOGLE_OAUTH_REFRESH_TOKEN={refresh_token}\n"

with open(env_path, "w") as f:
    f.write(env_content)

print("\n✅ Refresh token saved to .env")
print("You can now run the bot — it will use OAuth to create new Sheets files.\n")
