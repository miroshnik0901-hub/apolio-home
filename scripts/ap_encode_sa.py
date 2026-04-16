"""
encode_service_account.py — encodes Google service account JSON to base64
for use as GOOGLE_SERVICE_ACCOUNT env variable.

Usage:
  python encode_service_account.py path/to/service_account.json
"""

import sys
import base64
import json


def main():
    if len(sys.argv) < 2:
        print("Usage: python encode_service_account.py service_account.json")
        sys.exit(1)

    path = sys.argv[1]
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)

    encoded = base64.b64encode(json.dumps(data).encode()).decode()

    print(f"\n✅ Encoded service account")
    print(f"   Project: {data.get('project_id', '?')}")
    print(f"   Email:   {data.get('client_email', '?')}")
    print(f"\nAdd to .env:")
    print(f"GOOGLE_SERVICE_ACCOUNT={encoded}")

    # Write to .env if it exists
    env_line = f"GOOGLE_SERVICE_ACCOUNT={encoded}"
    if input("\nWrite to .env automatically? (y/n): ").lower() == "y":
        env_path = ".env"
        if open(env_path).read().find("GOOGLE_SERVICE_ACCOUNT=") >= 0:
            lines = open(env_path).read().splitlines()
            lines = [env_line if l.startswith("GOOGLE_SERVICE_ACCOUNT=") else l for l in lines]
            open(env_path, "w").write("\n".join(lines) + "\n")
        else:
            open(env_path, "a").write(f"\n{env_line}\n")
        print("✅ Written to .env")


if __name__ == "__main__":
    main()
