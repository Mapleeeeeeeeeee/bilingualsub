import { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/api/client';
import { parseSrt, serializeSrt } from '@/utils/srt';
import type { SrtEntry } from '@/types';

interface SubtitleEditorProps {
  jobId: string;
}

export function SubtitleEditor({ jobId }: SubtitleEditorProps) {
  const { t } = useTranslation();
  const [originalEntries, setOriginalEntries] = useState<SrtEntry[]>([]);
  const [entries, setEntries] = useState<SrtEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadSrt() {
      setLoading(true);
      setError(null);
      try {
        const raw = await apiClient.fetchSrtContent(jobId);
        if (cancelled) return;
        const parsed = parseSrt(raw);
        setOriginalEntries(parsed);
        setEntries(parsed);
      } catch {
        if (!cancelled) {
          setError(t('editor.loadError'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadSrt();
    return () => {
      cancelled = true;
    };
  }, [jobId, t]);

  const hasEdits = useMemo(() => {
    if (entries.length !== originalEntries.length) return false;
    return entries.some((entry, i) => entry.translated !== originalEntries[i].translated);
  }, [entries, originalEntries]);

  const handleTranslatedChange = useCallback((index: number, value: string) => {
    setEntries(prev =>
      prev.map((entry, i) => (i === index ? { ...entry, translated: value } : entry))
    );
  }, []);

  const handleReset = useCallback(() => {
    setEntries(originalEntries);
  }, [originalEntries]);

  const handleDownload = useCallback(() => {
    const content = serializeSrt(entries);
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'bilingualsub-edited.srt';
    a.click();
    URL.revokeObjectURL(url);
  }, [entries]);

  if (loading) {
    return <p className="text-sm text-gray-500">{t('editor.loading')}</p>;
  }

  if (error) {
    return <p className="text-sm text-red-500">{error}</p>;
  }

  if (entries.length === 0) {
    return <p className="text-sm text-gray-500">{t('editor.empty')}</p>;
  }

  return (
    <div>
      <h3 className="text-lg font-semibold text-gray-900 mb-4">{t('editor.title')}</h3>

      <div className="max-h-96 overflow-y-auto space-y-3 mb-4">
        {entries.map((entry, i) => (
          <div key={entry.index} className="border border-gray-200 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2 text-xs text-gray-400">
              <span>#{entry.index}</span>
              <span>
                {entry.startTime} → {entry.endTime}
              </span>
            </div>
            <textarea
              value={entry.translated}
              onChange={e => handleTranslatedChange(i, e.target.value)}
              rows={1}
              className="w-full px-2 py-1 text-sm border border-gray-300 rounded resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            {entry.original && <p className="mt-1 text-xs text-gray-400">{entry.original}</p>}
          </div>
        ))}
      </div>

      {hasEdits && <p className="text-xs text-amber-600 mb-3">{t('editor.unsavedHint')}</p>}

      <div className="flex gap-3">
        <button
          onClick={handleReset}
          disabled={!hasEdits}
          className="px-4 py-2 text-sm border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {t('editor.reset')}
        </button>
        <button
          onClick={handleDownload}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          {t('editor.download')}
        </button>
      </div>
    </div>
  );
}
