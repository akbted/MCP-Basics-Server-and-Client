import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

class Settings:
    HF_TOKEN = os.getenv("HF_TOKEN")
    OPENROUTER = os.getenv("OPENROUTER_API")
    OPENPROJECT_APIROOT = os.getenv("OPENPROJECT_APIROOT")
    OPENPROJECT_TOKEN = os.getenv("OPENPROJECT_TOKEN")
    OUTPUT_DIR = ROOT / "outputs" 
    OUTPUT_FILE = ROOT / "outputs" / "project_details.json"

settings = Settings()