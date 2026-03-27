'use client';

import { useState, useRef, useCallback } from 'react';

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'https://querate-backend-862135384918.us-central1.run.app';

interface Artist {
  id: string;
  name: string;
  distance: number;
}

interface SearchResult {
  query: string;
  artists: Artist[];
}

interface PhotoResult {
  mood_description: string;
  artists: Artist[];
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult | null>(null);
  const [photoResult, setPhotoResult] = useState<PhotoResult | null>(null);
  const [loading, setLoading] = useState(false);

  // Camera state
  const [cameraOpen, setCameraOpen] = useState(false);
  const [capturedImage, setCapturedImage] = useState<string | null>(null); // base64 data URL
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // --- Text search ---
  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setPhotoResult(null);
    try {
      const res = await fetch(`${BACKEND}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });
      const data = await res.json();
      setResults(data);
    } catch (error) {
      console.error(error);
    }
    setLoading(false);
  };

  // --- Camera ---
  const openCamera = useCallback(async () => {
    setCapturedImage(null);
    setPhotoResult(null);
    setCameraOpen(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch {
      alert('Could not access camera.');
      setCameraOpen(false);
    }
  }, []);

  const closeCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCameraOpen(false);
  }, []);

  const capturePhoto = useCallback(() => {
    if (!videoRef.current) return;
    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    canvas.getContext('2d')!.drawImage(videoRef.current, 0, 0);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
    setCapturedImage(dataUrl);
    closeCamera();
  }, [closeCamera]);

  const analyzeMood = async () => {
    if (!capturedImage) return;
    setLoading(true);
    setResults(null);
    try {
      // Strip the "data:image/jpeg;base64," prefix
      const base64 = capturedImage.split(',')[1];
      const res = await fetch(`${BACKEND}/search-by-photo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_base64: base64 }),
      });
      const data = await res.json();
      setPhotoResult(data);
    } catch (error) {
      console.error(error);
    }
    setLoading(false);
  };

  const ArtistList = ({ artists }: { artists: Artist[] }) => (
    <div className="space-y-4">
      {artists.map((artist, i) => (
        <div key={artist.id} className="bg-gray-900 p-4 rounded">
          <div className="flex justify-between items-center">
            <div>
              <p className="text-sm text-gray-400">#{i + 1}</p>
              <p className="text-xl font-bold">{artist.name}</p>
            </div>
            <p className="text-sm text-gray-400">Distance: {artist.distance.toFixed(3)}</p>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="min-h-screen bg-black text-white p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-4xl font-bold mb-8">Taste Mirror</h1>

        {/* Text search */}
        <form onSubmit={handleSearch} className="mb-6">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Describe your vibe... (e.g., dark and experimental)"
            className="w-full px-4 py-3 bg-gray-900 border border-gray-700 rounded text-white mb-4"
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full px-4 py-3 bg-white text-black font-bold rounded hover:bg-gray-200 disabled:opacity-50"
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>

        {/* Divider */}
        <div className="flex items-center gap-4 mb-6">
          <div className="flex-1 border-t border-gray-700" />
          <span className="text-gray-500 text-sm">or</span>
          <div className="flex-1 border-t border-gray-700" />
        </div>

        {/* Camera section */}
        <div className="mb-8">
          {!cameraOpen && !capturedImage && (
            <button
              onClick={openCamera}
              className="w-full px-4 py-3 bg-gray-900 border border-gray-700 text-white font-bold rounded hover:bg-gray-800"
            >
              Use Camera to Detect Mood
            </button>
          )}

          {cameraOpen && (
            <div className="space-y-4">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                className="w-full rounded border border-gray-700"
              />
              <div className="flex gap-4">
                <button
                  onClick={capturePhoto}
                  className="flex-1 px-4 py-3 bg-white text-black font-bold rounded hover:bg-gray-200"
                >
                  Capture
                </button>
                <button
                  onClick={closeCamera}
                  className="px-4 py-3 bg-gray-900 border border-gray-700 text-white rounded hover:bg-gray-800"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {capturedImage && (
            <div className="space-y-4">
              <img src={capturedImage} alt="Captured" className="w-full rounded border border-gray-700" />
              <div className="flex gap-4">
                <button
                  onClick={analyzeMood}
                  disabled={loading}
                  className="flex-1 px-4 py-3 bg-white text-black font-bold rounded hover:bg-gray-200 disabled:opacity-50"
                >
                  {loading ? 'Analyzing...' : 'Analyze Mood'}
                </button>
                <button
                  onClick={() => { setCapturedImage(null); setPhotoResult(null); openCamera(); }}
                  className="px-4 py-3 bg-gray-900 border border-gray-700 text-white rounded hover:bg-gray-800"
                >
                  Retake
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Photo results */}
        {photoResult && (
          <div className="mb-8">
            <p className="text-gray-400 text-sm mb-1">Detected mood</p>
            <p className="text-lg italic mb-6 text-gray-200">"{photoResult.mood_description}"</p>
            <ArtistList artists={photoResult.artists} />
          </div>
        )}

        {/* Text search results */}
        {results && (
          <div>
            <h2 className="text-2xl font-bold mb-4">Results for: {results.query}</h2>
            <ArtistList artists={results.artists} />
          </div>
        )}
      </div>
    </div>
  );
}
