'use client';

import { useState } from 'react';

type StockResult = {
  symbol: string;
  name: string;
  price: number | null;
  change_percent: number | null;
  volume: number | null;
  ma5: number | null;
  ma20: number | null;
  signal: string;
  reason: string;
};

export default function HomePage() {
  const [symbols, setSymbols] = useState('2330,2317,2454,2303,2603,1301,1802');
  const [results, setResults] = useState<StockResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleScan = async () => {
    setLoading(true);
    setError('');
    setResults([]);

    try {
      const parsedSymbols = symbols
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const response = await fetch('http://127.0.0.1:8000/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols: parsedSymbols }),
      });

      if (!response.ok) {
        throw new Error(`API 錯誤: ${response.status}`);
      }

      const data: StockResult[] = await response.json();
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '未知錯誤');
    } finally {
      setLoading(false);
    }
  };

  const getSignalClass = (signal: string) => {
    switch (signal) {
      case '偏多':
        return 'bg-red-100 text-red-700 border-red-200';
      case '偏空':
        return 'bg-green-100 text-green-700 border-green-200';
      case '觀察':
        return 'bg-yellow-100 text-yellow-700 border-yellow-200';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-200';
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 px-6 py-10">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">台股選股系統</h1>
          <p className="mt-2 text-gray-600">
            輸入股票代碼，系統會抓取資料並做簡單技術面判斷
          </p>
        </div>

        <div className="rounded-2xl bg-white p-6 shadow-sm border border-gray-200">
          <label className="mb-2 block text-sm font-medium text-gray-700">
            股票代碼（用逗號分隔）
          </label>
          <textarea
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            rows={3}
            className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm text-gray-900 outline-none focus:border-blue-500"
            placeholder="例如：2330,2317,2454,2303"
          />

          <div className="mt-4 flex gap-3">
            <button
              onClick={handleScan}
              disabled={loading}
              className="rounded-xl bg-blue-600 px-5 py-3 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {loading ? '掃描中...' : '開始掃描'}
            </button>
          </div>

          {error && (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>

        <div className="mt-8">
          <h2 className="mb-4 text-xl font-semibold text-gray-900">掃描結果</h2>

          {results.length === 0 && !loading && (
            <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-gray-500">
              尚未產生結果
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {results.map((stock) => (
              <div
                key={stock.symbol}
                className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-gray-900">{stock.symbol}</h3>
                    <p className="text-sm text-gray-500">{stock.name}</p>
                  </div>
                  <span
                    className={`rounded-full border px-3 py-1 text-xs font-semibold ${getSignalClass(stock.signal)}`}
                  >
                    {stock.signal}
                  </span>
                </div>

                <div className="mt-4 space-y-2 text-sm text-gray-700">
                  <div className="flex justify-between">
                    <span>現價</span>
                    <span className="font-medium">{stock.price ?? '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>漲跌幅</span>
                    <span className="font-medium">
                      {stock.change_percent !== null ? `${stock.change_percent}%` : '-'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>成交量</span>
                    <span className="font-medium">
                      {stock.volume !== null ? stock.volume.toLocaleString() : '-'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>MA5</span>
                    <span className="font-medium">{stock.ma5 ?? '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>MA20</span>
                    <span className="font-medium">{stock.ma20 ?? '-'}</span>
                  </div>
                </div>

                <div className="mt-4 rounded-xl bg-gray-50 p-3 text-sm text-gray-600">
                  <span className="font-medium text-gray-800">判斷：</span>
                  {stock.reason}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}