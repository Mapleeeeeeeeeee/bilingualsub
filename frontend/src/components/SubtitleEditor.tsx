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
    return (
      <p className="text-center text-gray-400 font-serif italic py-12">{t('editor.loading')}</p>
    );
  }

  if (error) {
    return <p className="text-center text-red-500 py-12">{error}</p>;
  }

  if (entries.length === 0) {
    return <p className="text-center text-gray-400 py-12">{t('editor.empty')}</p>;
  }

  return (
    <div className="space-y-12">
      <div className="flex items-center justify-between border-b border-black pb-4">
        <h3 className="text-2xl font-serif">{t('editor.title')}</h3>
        <div className="flex gap-8">
          <button
            onClick={handleReset}
            disabled={!hasEdits}
            className="text-sm uppercase tracking-widest hover:text-red-600 disabled:opacity-30 transition-colors"
          >
            {t('editor.reset')}
          </button>
          <button
            onClick={handleDownload}
            className="text-sm uppercase tracking-widest hover:text-green-600 transition-colors"
          >
            {t('editor.download')}
          </button>
        </div>
      </div>

      <div className="space-y-8">
        {entries.map((entry, i) => (
          <div key={entry.index} className="grid grid-cols-1 md:grid-cols-12 gap-8 group">
            {/* Metadata Column */}
            <div className="md:col-span-3 pt-2">
              <div className="flex flex-col gap-1">
                <span className="text-xs font-bold text-gray-300 group-hover:text-black transition-colors">
                  #{entry.index}
                </span>
                <span className="font-mono text-xs text-gray-400">{entry.startTime}</span>
                <span className="font-mono text-xs text-gray-400">{entry.endTime}</span>
              </div>
            </div>

            {/* Content Column */}
            <div className="md:col-span-9 space-y-4">
              <textarea
                value={entry.translated}
                onChange={e => handleTranslatedChange(i, e.target.value)}
                rows={Math.max(2, Math.ceil(entry.translated.length / 60))}
                className="w-full bg-transparent text-xl md:text-2xl font-serif text-black placeholder-gray-300 focus:outline-none focus:bg-gray-50 p-2 -ml-2 rounded transition-colors resize-none leading-relaxed"
              />
              {entry.original && (
                <p className="text-sm text-gray-400 font-sans leading-relaxed">{entry.original}</p>
              )}
            </div>
          </div>
        ))}
      </div>

      {hasEdits && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-black text-white px-6 py-3 rounded-full shadow-2xl animate-bounce">
          <span className="text-sm font-medium">{t('editor.unsavedHint')}</span>
        </div>
      )}
    </div>
  );
}
