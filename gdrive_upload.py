# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "google-api-python-client",
#   "google-auth",
# ]
# ///
"""Загружает файл на Google Drive в указанную папку."""
import sys
import os
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

KEY_FILE = Path(__file__).parent / "secrets" / "gdrive-key.json"
FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def upload(file_path: str) -> str:
    if not FOLDER_ID:
        raise RuntimeError("GDRIVE_FOLDER_ID не задан")
    creds = service_account.Credentials.from_service_account_file(str(KEY_FILE), scopes=SCOPES)
    service = build("drive", "v3", credentials=creds)
    name = Path(file_path).name
    meta = {"name": name, "parents": [FOLDER_ID]}
    media = MediaFileUpload(file_path, mimetype="application/zip", resumable=True)
    file = service.files().create(body=meta, media_body=media, fields="id,name,size").execute()
    print(f"✅ Загружено: {file['name']} (id={file['id']}, {int(file.get('size',0))//1024//1024} МБ)")
    return file["id"]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: uv run gdrive_upload.py <путь_к_файлу>")
        sys.exit(1)
    upload(sys.argv[1])
