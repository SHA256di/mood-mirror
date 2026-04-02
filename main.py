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

# Config — all values come from Cloud Run environment variables
PROJECT_ID = os.environ["GCP_PROJECT_ID"]
REGION = os.environ["GCP_REGION"]
APP_SECRET = os.environ["MY_APP_SECRET"]
COLLECTION = f"projects/{PROJECT_ID}/locations/{REGION}/collections/music-taste-v3"
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
            filter={"affinity_tier": {"$in": ["obsessed", "love"]}},
            output_fields=vectorsearch_v1beta.OutputFields(
                data_fields=["track", "artist", "album"]
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
        })

    return tracks

@app.post("/search-by-photo")
@limiter.limit("5/minute")
async def search_by_photo(request: Request, body: PhotoRequest):
    """Analyze facial expression in photo → mood text → artist search."""
    try:
        image_bytes = base64.b64decode(body.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image.")

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((384, 384), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    gemini = GenerativeModel("gemini-2.5-flash")
    image_part = Part.from_data(data=image_bytes, mime_type="image/jpeg")
    combined_prompt = (
        "You are analyzing a person's facial expression to create a personalized playlist.\n\n"
        "First, examine their expression carefully:\n"
        "- Primary emotion and micro-expressions\n"
        "- Energy level and emotional texture\n"
        "- Inner mood and atmosphere\n\n"
        "Then provide:\n"
        "1. MOOD: 2-3 sentences describing their emotional vibe in vivid, sensory language\n"
        "2. TITLE: A short, creative music playlist title (2-5 words max) that captures this mood\n\n"
        "Format your response exactly like this:\n"
        "MOOD: [your mood description]\n"
        "TITLE: [your playlist title]"
    )

    response = gemini.generate_content([image_part, combined_prompt])
    text = response.text.strip()

    # Parse response with error handling
    try:
        mood_description = text.split("TITLE:")[0].replace("MOOD:", "").strip()
        playlist_title = text.split("TITLE:")[1].strip()
    except IndexError:
        # Fallback if Gemini doesn't format correctly
        mood_description = text
        playlist_title = "Your Mood Playlist"

    tracks = embed_and_search(mood_description, body.num_results)

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
