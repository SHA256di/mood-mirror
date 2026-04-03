'use client';

import { useState, useRef, useCallback, useEffect } from 'react';

const BACKEND = '/api/backend';
const APP_SECRET = process.env.NEXT_PUBLIC_APP_SECRET ?? '';

interface Track {
  spotify_uri: string;
  track: string | null;
  artist: string | null;
  album: string | null;
}

interface PhotoResult {
  mood_description: string;
  playlist_title: string;
  tracks: Track[];
}

export default function Home() {
  const [photoResult, setPhotoResult] = useState<PhotoResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCameraActive(true);
    } catch {
      alert('Could not access camera.');
    }
  }, []);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCameraActive(false);
  }, []);

  // Auto-start camera on mount
  useEffect(() => {
    startCamera();
    return () => stopCamera();
  }, [startCamera, stopCamera]);

  // Show feedback modal once, 7s after playlist loads
  useEffect(() => {
    if (!photoResult?.tracks) return;
    if (localStorage.getItem('feedback_shown')) return;
    const timer = setTimeout(() => {
      setShowFeedback(true);
      localStorage.setItem('feedback_shown', 'true');
    }, 15000);
    return () => clearTimeout(timer);
  }, [photoResult]);

  // Keep video srcObject in sync when camera is active
  useEffect(() => {
    if (cameraActive && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [cameraActive]);

  const mirrorMood = async () => {
    if (!videoRef.current) return;

    // Capture frame from video
    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    canvas.getContext('2d')!.drawImage(videoRef.current, 0, 0);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
    setCapturedImage(dataUrl);
    stopCamera();

    setLoading(true);
    try {
      const base64 = dataUrl.split(',')[1];
      const res = await fetch(`${BACKEND}/search-by-photo`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-app-secret': APP_SECRET,
        },
        body: JSON.stringify({ image_base64: base64 }),
      });
      if (!res.ok) {
        const text = await res.text();
        console.error(`Backend error ${res.status}:`, text);
        throw new Error(text);
      }
      const data = await res.json();
      setPhotoResult(data);
    } catch (error) {
      console.error(error);
    }
    setLoading(false);
  };

  const resetMood = useCallback(() => {
    setCapturedImage(null);
    setPhotoResult(null);
    startCamera();
  }, [startCamera]);

  return (
    <div className="min-h-screen bg-white text-black flex flex-col items-center px-4 pt-6 pb-8">

      {/* Title */}
      <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-center text-black mb-6 leading-relaxed w-full self-stretch px-4 break-words">
        ⋆˚࿔ 📀 🎧 ⋆˚ ✨ 🪞 𝓂ℴℴ𝒹 𝓂𝒾𝓇𝓇ℴ𝓇 🪞 ✨ ˚⋆ 🎧 📀 ࿔˚.
      </h1>

      <div className="flex flex-col items-center w-full max-w-3xl">

        {/* Camera / captured image box — hidden once results are ready */}
        {!photoResult && (
          <div className="w-full aspect-video bg-black rounded-2xl overflow-hidden border border-gray-200 shadow-sm">
            {capturedImage ? (
              <img src={capturedImage} alt="Captured" className="w-full h-full object-cover" />
            ) : (
              <video ref={videoRef} autoPlay playsInline className="w-full h-full object-cover" />
            )}
          </div>
        )}

        {!photoResult ? (
          <>
            {/* Mirror my mood */}
            {!capturedImage && (
              <button
                onClick={mirrorMood}
                className="mt-5 w-full px-4 py-3 bg-black text-white font-semibold rounded-full hover:bg-gray-800 transition"
              >
                mirror my mood
              </button>
            )}

            {/* Loading state */}
            {loading && (
              <p className="mt-4 text-sm text-gray-400 animate-pulse">reading your reflection...</p>
            )}

            {/* My mood's changed (retake) */}
            {capturedImage && !loading && (
              <button
                onClick={resetMood}
                className="mt-5 w-full px-4 py-3 border border-gray-300 text-black font-medium rounded-full hover:bg-gray-50 transition"
              >
                my mood's changed
              </button>
            )}
          </>
        ) : (
          /* ── Spotify-style playlist result ── */
          <div className="w-full bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">

            {/* Playlist header */}
            <div className="flex gap-8 items-end p-10 bg-gradient-to-b from-gray-100 to-white">
              {capturedImage && (
                <img
                  src={capturedImage}
                  alt="Your mood"
                  className="w-52 h-52 object-cover rounded-xl shadow-lg flex-shrink-0"
                />
              )}
              <div className="min-w-0">
                <h2 className="text-4xl font-extrabold leading-tight text-black mb-3">
                  {photoResult.playlist_title}
                </h2>
                <p className="text-base text-gray-500 italic">
                  {photoResult.mood_description}
                </p>
                <p className="text-sm text-gray-400 mt-3">
                  {photoResult.tracks.length} songs
                </p>
              </div>
            </div>

            {/* Column headers */}
            <div className="grid grid-cols-[2.5rem_1fr_1fr_1fr] items-center text-xs text-gray-400 uppercase tracking-widest px-6 py-3 border-t border-gray-100">
              <span>#</span>
              <span>Track</span>
              <span>Artist</span>
              <span>Album</span>
            </div>

            {/* Scrollable track list */}
            <div className="divide-y divide-gray-50 max-h-96 overflow-y-auto">
              {photoResult.tracks.map((track, i) => (
                <a
                  key={track.spotify_uri}
                  href={`https://open.spotify.com/track/${track.spotify_uri.split(':').pop()}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="grid grid-cols-[2.5rem_1fr_1fr_1fr] items-center px-6 py-4 hover:bg-gray-50 transition"
                >
                  <span className="text-sm text-gray-400">{i + 1}</span>
                  <span className="text-sm font-semibold text-black truncate pr-4">{track.track ?? '—'}</span>
                  <span className="text-sm text-gray-600 truncate pr-4">{track.artist ?? '—'}</span>
                  <span className="text-sm text-gray-500 truncate pr-4">{track.album ?? '—'}</span>
                </a>
              ))}
            </div>

            {/* My mood's changed */}
            <div className="px-10 py-6 border-t border-gray-100">
              <button
                onClick={resetMood}
                className="w-full px-4 py-4 border border-gray-300 text-black font-medium rounded-full hover:bg-gray-50 transition text-base"
              >
                my mood's changed
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Feedback modal */}
      {showFeedback && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full relative">
            <button
              onClick={() => setShowFeedback(false)}
              className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition z-10"
              aria-label="Close"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <div className="p-6 pb-4">
              <h3 className="text-xl font-semibold text-gray-900">Quick feedback?</h3>
              <p className="text-sm text-gray-600 mt-1">Takes 30 seconds – helps me improve this! 🎵</p>
            </div>
            <div className="px-6 pb-2">
              <iframe
                src="https://tally.so/embed/rjLvLo?alignLeft=1&hideTitle=1&transparentBackground=1&dynamicHeight=1"
                width="100%"
                height="500"
                frameBorder={0}
                marginHeight={0}
                marginWidth={0}
                title="Feedback Survey"
                className="overflow-hidden"
              />
            </div>
            <div className="px-6 pb-6 pt-2">
              <button
                onClick={() => setShowFeedback(false)}
                className="w-full text-center text-sm text-gray-500 hover:text-gray-700 transition py-2"
              >
                Skip for now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );

}
