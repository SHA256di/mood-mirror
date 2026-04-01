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
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Config — all values come from Cloud Run environment variables
PROJECT_ID = os.environ["GCP_PROJECT_ID"]
REGION = os.environ["GCP_REGION"]
ENDPOINT_ID = os.environ["VERTEX_ENDPOINT_ID"]
DEPLOYED_INDEX_ID = os.environ["VERTEX_DEPLOYED_INDEX_ID"]
APP_SECRET = os.environ["MY_APP_SECRET"]
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
aiplatform.init(project=PROJECT_ID, location=REGION)
vertexai.init(project=PROJECT_ID, location=REGION)

class QueryRequest(BaseModel):
    query: str
    num_results: int = 10

class PhotoRequest(BaseModel):
    image_base64: str  # base64-encoded image (no data URI prefix)
    num_results: int = 10

def embed_and_search(query: str, num_results: int):
    """Shared helper: embed text → vector search → formatted tracks."""
    model = TextEmbeddingModel.from_pretrained("text-embedding-005")
    query_embedding = model.get_embeddings([query])[0].values

    index_endpoint = aiplatform.MatchingEngineIndexEndpoint(
        index_endpoint_name=f"projects/{PROJECT_ID}/locations/{REGION}/indexEndpoints/{ENDPOINT_ID}"
    )

    results = index_endpoint.find_neighbors(
        deployed_index_id=DEPLOYED_INDEX_ID,
        queries=[query_embedding],
        num_neighbors=num_results,
    )

    tracks = []
    for neighbor in results[0]:
        meta = {r.name: r.allow_tokens[0] for r in (neighbor.restricts or []) if r.allow_tokens}

        # Parse "Track by Artist from Album. ..." from the content restrict
        track_name = meta.get("track")
        artist_name = meta.get("artist")
        album_name = meta.get("album")

        if not (track_name and artist_name and album_name):
            content = meta.get("content", "")
            first_sentence = content.split(". ")[0]  # e.g. "Mean by $NOT from Beautiful Havoc"
            try:
                track_part, rest = first_sentence.split(" by ", 1)
                artist_part, album_part = rest.split(" from ", 1)
                track_name = track_name or track_part.strip()
                artist_name = artist_name or artist_part.strip()
                album_name = album_name or album_part.strip()
            except ValueError:
                pass

        tracks.append({
            "spotify_uri": neighbor.id,
            "track": track_name,
            "artist": artist_name,
            "album": album_name,
            "distance": float(neighbor.distance),
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

    track_names_str = ", ".join(
        f"{t['track']} by {t['artist']}" for t in tracks[:6] if t.get("track")
    )
    title_prompt = (
        f"Based on these tracks: {track_names_str}, and this mood: \"{mood_description}\", "
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
    """Returns raw neighbor data from the index for a test query. Remove before prod."""
    model = TextEmbeddingModel.from_pretrained("text-embedding-005")
    query_embedding = model.get_embeddings(["sad rainy night"])[0].values

    index_endpoint = aiplatform.MatchingEngineIndexEndpoint(
        index_endpoint_name=f"projects/{PROJECT_ID}/locations/{REGION}/indexEndpoints/{ENDPOINT_ID}"
    )
    results = index_endpoint.find_neighbors(
        deployed_index_id=DEPLOYED_INDEX_ID,
        queries=[query_embedding],
        num_neighbors=1,
    )

    neighbor = results[0][0]
    return {
        "id": neighbor.id,
        "distance": float(neighbor.distance),
        "restricts": [
            {"name": r.name, "allow_tokens": r.allow_tokens, "deny_tokens": r.deny_tokens}
            for r in (neighbor.restricts or [])
        ],
        "crowding_tag": getattr(neighbor, "crowding_tag", None),
    }
