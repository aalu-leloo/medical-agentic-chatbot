import os
import certifi
from dotenv import load_dotenv
load_dotenv()
### AUTOMATIC SSL FIX FOR  PYTHON ENVIROMENT
ssl_cert=os.environ.get('SSL_CERT_FILE')
if ssl_cert and not os.path.exists(ssl_cert):
    os.environ['SSL_CERT_FILE']=certifi.where()
elif not ssl_cert:
    os.environ['SSL_CERT_FILE']=certifi.where()
###---------------------------------------------
from pydantic_settings import BaseSettings,SettingsConfigDict
class Settings(BaseSettings):
    gemini_api_key:str =""
    pinecone_api_key:str="" 
    tavily_api_key:str=""
    pinecone_index:str="medical-agent-demo"
    gemini_chat_model:str="gemini-flash-lite-latest"
    gemini_embed_model:str="gemini-embedding-2"
    gemini_vision_model:str="gemini-3.8-flash"
    api_tokens:str=''
    allowed_origins:str="http://localhost:8000,http://127.0.0.1:8000"
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")
settings=Settings()    