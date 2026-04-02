import base64
import io
import os
from PIL import Image
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from pydantic import BaseModel
from google.cloud import vectorsearch_v1beta
from vertexai.language_models import TextEmbeddingModel
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # not needed in Cloud Run
print("=" * 50)
print(f"MY_APP_SECRET from env: [{os.environ.get('MY_APP_SECRET')}]")
print(f"Expected in header: x-app-secret: {os.environ.get('MY_APP_SECRET')}")
print("=" * 50)

# Config — all values come from Cloud Run environment variables
PROJECT_ID = os.environ["GCP_PROJECT_ID"]
REGION = os.environ["GCP_REGION"]
APP_SECRET = os.environ["MY_APP_SECRET"]
COLLECTION = f"projects/{PROJECT_ID}/locations/{REGION}/collections/music-taste-v2"
_raw_origins = os.getenv("CORS_ORIGINS", "https://querate.ai,https://www.querate.ai")
CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS must be outermost so preflight OPTIONS requests are handled before secret check
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*", "x-app-secret"],
)

# Shared-secret guard — skips OPTIONS (preflight) and /health
class SecretMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path == "/health":
            return await call_next(request)
        token = request.headers.get("x-app-secret", "")
        print(f"DEBUG: Received token: [{token}]")
        print(f"DEBUG: Expected token: [{APP_SECRET}]")
        print(f"DEBUG: Tokens match: {token == APP_SECRET}")
        print(f"DEBUG: Token length: {len(token)}, Expected length: {len(APP_SECRET)}")
        
        if token != APP_SECRET:
            return Response(content="Unauthorized", status_code=401)
        return await call_next(request)

app.add_middleware(SecretMiddleware)

# Initialize
vertexai.init(project=PROJECT_ID, location=REGION)
search_client = vectorsearch_v1beta.DataObjectSearchServiceClient()

class QueryRequest(BaseModel):
    query: str
    num_results: int = 10

class PhotoRequest(BaseModel):
    image_base64: str  # base64-encoded image (no data URI prefix)
    num_results: int = 15

def embed_and_search(query: str, num_results: int):
    """Shared helper: embed text → vector search → formatted tracks."""
    model = TextEmbeddingModel.from_pretrained("text-embedding-005")
    query_embedding = model.get_embeddings([query])[0].values

    request = vectorsearch_v1beta.SearchDataObjectsRequest(
        parent=COLLECTION,
        vector_search=vectorsearch_v1beta.VectorSearch(
            search_field="embedding",
            vector=vectorsearch_v1beta.DenseVector(values=query_embedding),
            top_k=num_results,
            output_fields=vectorsearch_v1beta.OutputFields(
                data_fields=["track", "artist", "album", "affinity_score", "content"]
            ),
        ),
    )

    response = search_client.search_data_objects(request)

    tracks = []
    for result in response.results:
        data = result.data_object.data
        spotify_uri = result.data_object.name.split("/")[-1]
        tracks.append({
            "spotify_uri":    spotify_uri,
            "track":          data.get("track"),
            "artist":         data.get("artist"),
            "album":          data.get("album"),
            "affinity_score": data.get("affinity_score"),
        })

    return tracks


@app.post("/search")
@limiter.limit("20/minute")
async def search(request: Request, body: QueryRequest):
    """Search for tracks by vibe query."""
    tracks = embed_and_search(body.query, body.num_results)
    return {"query": body.query, "tracks": tracks}


@app.post("/search-by-photo")
@limiter.limit("5/minute")
async def search_by_photo(request: Request, body: PhotoRequest):
    """Analyze facial expression in photo → mood text → artist search."""
    try:
        image_bytes = base64.b64decode(body.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image.")

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((512, 512), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    gemini = GenerativeModel("gemini-2.5-flash")
    image_part = Part.from_data(data=image_bytes, mime_type="image/jpeg")
    prompt = (
        "Look at the facial expression in this photo. "
        "Describe the person's mood and emotional vibe in 1-2 sentences "
        "Be specific and evocative. Only output the description, nothing else."
    )

    response = gemini.generate_content([image_part, prompt])
    mood_description = response.text.strip()

    tracks = embed_and_search(mood_description, body.num_results)

    tracks_str = ", ".join(
        f"{t['track']} by {t['artist']}" for t in tracks[:6] if t.get("track") and t.get("artist")
    )
    title_prompt = (
        f"Based on these tracks: {tracks_str}, and this mood: \"{mood_description}\", "
        "create a short, creative Spotify playlist title. "
        "Only output the title, nothing else. No quotes, no punctuation at the end."
    )
    title_response = gemini.generate_content(title_prompt)
    playlist_title = title_response.text.strip()

    return {
        "mood_description": mood_description,
        "playlist_title": playlist_title,
        "tracks": tracks,
    }

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)


@app.get("/debug-neighbor")
async def debug_neighbor():
    """Returns raw result data from VS2.0 for a test query."""
    try:
        tracks = embed_and_search("sad rainy night", 1)
        return {"result": tracks[0] if tracks else None}
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}