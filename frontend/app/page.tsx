'use client';

import { useState } from 'react';

interface Artist {
  id: string;
  name: string;
  distance: number;
}

interface SearchResult {
  query: string;
  artists: Artist[];
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const res = await fetch('https://querate-backend-862135384918.us-central1.run.app/search', {
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

  return (
    <div className="min-h-screen bg-black text-white p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-4xl font-bold mb-8">Taste Mirror</h1>
        
        <form onSubmit={handleSearch} className="mb-8">
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

        {results && (
          <div>
            <h2 className="text-2xl font-bold mb-4">Results for: {results.query}</h2>
            <div className="space-y-4">
              {results.artists.map((artist, i) => (
                <div key={artist.id} className="bg-gray-900 p-4 rounded">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm text-gray-400">#{i + 1}</p>
                      <p className="text-xl font-bold">{artist.name}</p>
                    </div>
                    <p className="text-sm text-gray-400">
                      Distance: {artist.distance.toFixed(3)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}