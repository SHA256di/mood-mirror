import base64
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel
import vertexai
from vertexai.generative_models import GenerativeModel, Part

# Config
PROJECT_ID = "querate-ai"
REGION = "us-central1"
ENDPOINT_ID = "2822536508454469632"
DEPLOYED_INDEX_ID = "artists_deployed_1774557049856"

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://querate-ai.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    """Shared helper: embed text → vector search → formatted artists."""
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

    artists = []
    for neighbor in results[0]:
        artist_name = neighbor.id.replace("artist_", "").replace("_", " ").title()
        artists.append({
            "id": neighbor.id,
            "name": artist_name,
            "distance": float(neighbor.distance)
        })
    return artists


@app.post("/search")
async def search(request: QueryRequest):
    """Search for artists by vibe query."""
    artists = embed_and_search(request.query, request.num_results)
    return {"query": request.query, "artists": artists}


@app.post("/search-by-photo")
async def search_by_photo(request: PhotoRequest):
    """Analyze facial expression in photo → mood text → artist search."""
    try:
        image_bytes = base64.b64decode(request.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image.")

    gemini = GenerativeModel("gemini-2.5-flash")
    image_part = Part.from_data(data=image_bytes, mime_type="image/jpeg")
    prompt = (
        "Look at the facial expression in this photo. "
        "Describe the person's mood and emotional vibe in 1-2 sentences "
        "Be specific and evocative. Only output the description, nothing else."
    )
    response = gemini.generate_content([image_part, prompt])
    mood_description = response.text.strip()

    artists = embed_and_search(mood_description, request.num_results)
    return {
        "mood_description": mood_description,
        "artists": artists,
    }

@app.get("/health")
def health():
    return {"status": "ok"}
