import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter
from langchain_ollama import ChatOllama

import logging

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)

logger = logging.getLogger(name=__name__)

logger.info("ROOT File Path: %s", ROOT)

class Settings:
    HF_TOKEN = os.getenv("HF_TOKEN")
    OPENROUTER = os.getenv("OPENROUTER_API")
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