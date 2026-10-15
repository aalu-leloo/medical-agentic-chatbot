from functools import lru_cache
from pinecone import Pinecone,ServerlessSpec
from google import genai
from app.config import settings
import time
from google.genai import errors
@lru_cache()
def clients():
    if not settings.gemini_api_key or not settings.pinecone_api_key:
        raise ValueError("gemini or pinecone api key must be set in the environment")
    return genai.Client(api_key=settings.gemini_api_key) ,Pinecone(api_key=settings.pinecone_api_key)
def ensure_index():
    gc,pc=clients()
    if not pc.has_index(settings.pinecone_index):
       pc.create_index(name=settings.pinecone_index, dimension=3072, metric="cosine", spec=ServerlessSpec(cloud="aws", region="us-east-1"))
    return pc.index(settings.pinecone_index)
def embed(texts):
    ai,_=clients()
    for attempt in range(6):
        try:
            res = ai.models.embed_content(
                model=settings.gemini_embed_model,
                contents=texts,
            )
            return [e.values for e in res.embeddings]
        except errors.APIError as e:
            if e.code == 429:
                wait = 65
            elif e.code in (500, 502, 503, 504):
                wait = min(10 * 2 ** attempt, 120)   # 10s, 20s, 40s, 80s, 120s...
            else:
                raise
            print(f"Error {e.code}, retrying in {wait}s (attempt {attempt + 1}/6)")
            time.sleep(wait)
    raise RuntimeError("Embedding failed after 6 retries")
def search_kb(query,top_k=5):
    index= ensure_index(),
    vector=embed([query])[0]
    result=index.query(vector=vector ,top_k=top_k,include_metadata=True)
    matches = getattr(result, "matches", None) or []
    return [{"page":m.metadata.get("page"),"text":m.metadata.get("text",""),"score":round(m.score,3), "source":"gale encyclopedia of medical knowledge"}
            for m in matches]
