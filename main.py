from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel

# Config
PROJECT_ID = "querate-ai"
REGION = "us-central1"
ENDPOINT_ID = "2822536508454469632"
DEPLOYED_INDEX_ID = "artists_deployed_1774557049856"

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://querate-ai.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize
aiplatform.init(project=PROJECT_ID, location=REGION)

class QueryRequest(BaseModel):
    query: str
    num_results: int = 10

@app.post("/search")
async def search(request: QueryRequest):
    """Search for artists by vibe query"""
    
    # Embed query
    model = TextEmbeddingModel.from_pretrained("text-embedding-005")
    query_embedding = model.get_embeddings([request.query])[0].values
    
    # Vector search
    index_endpoint = aiplatform.MatchingEngineIndexEndpoint(
        index_endpoint_name=f"projects/{PROJECT_ID}/locations/{REGION}/indexEndpoints/{ENDPOINT_ID}"
    )
    
    results = index_endpoint.find_neighbors(
        deployed_index_id=DEPLOYED_INDEX_ID,
        queries=[query_embedding],
        num_neighbors=request.num_results,
    )
    
    # Format results
    artists = []
    for neighbor in results[0]:
        artist_name = neighbor.id.replace("artist_", "").replace("_", " ").title()
        artists.append({
            "id": neighbor.id,
            "name": artist_name,
            "distance": float(neighbor.distance)
        })
    
    return {
        "query": request.query,
        "artists": artists
    }

@app.get("/health")
def health():
    return {"status": "ok"}
