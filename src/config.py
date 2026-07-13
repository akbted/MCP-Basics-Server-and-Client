import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter
from langchain_ollama import ChatOllama



load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

class Settings:
    HF_TOKEN = os.getenv("HF_TOKEN")
    OPENROUTER = os.getenv("OPENROUTER_API")
    OPENPROJECT_APIROOT = os.getenv("OPENPROJECT_APIROOT")
    OPENPROJECT_TOKEN = os.getenv("OPENPROJECT_TOKEN")
    OUTPUT_DIR = ROOT / "outputs" 
    OUTPUT_FILE = ROOT / "outputs" / "project_details.json"

    MODEL_NAME = os.getenv("MODEL_NAME")
    OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL")




settings = Settings()

def get_llmclient():
    return ChatOpenRouter(
        model=settings.MODEL_NAME,
        api_key=settings.OPENROUTER)

def get_ollamaclient():
    return ChatOllama(
        model=settings.OLLAMA_MODEL_NAME,
        temperature=0.1
    ) 