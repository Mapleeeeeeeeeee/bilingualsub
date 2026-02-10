import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/api/client';
import { FileType } from '@/constants';
import { parseSrt, serializeSrt, srtTimeToSeconds, isValidSrtTime } from '@/utils/srt';
import type { SrtEntry } from '@/types';

interface SubtitleEditorProps {
  jobId: string;
  onBurn: (srtContent: string) => void;
  isBurning: boolean;
}

export function SubtitleEditor({ jobId, onBurn, isBurning }: SubtitleEditorProps) {
  const { t } = useTranslation();
  const [originalEntries, setOriginalEntries] = useState<SrtEntry[]>([]);
  const [entries, setEntries] = useState<SrtEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const trackRef = useRef<TextTrack | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  const videoUrl = apiClient.getDownloadUrl(jobId, FileType.SOURCE_VIDEO);

  const activeEntryIndex = useMemo(() => {
    return entries.findIndex(
      entry =>
        currentTime >= srtTimeToSeconds(entry.startTime) &&
        currentTime <= srtTimeToSeconds(entry.endTime)
    );
  }, [entries, currentTime]);

  const handleEntryClick = useCallback((entry: SrtEntry) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = srtTimeToSeconds(entry.startTime);
    video.play();
  }, []);

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

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (!trackRef.current) {
      trackRef.current = video.addTextTrack('subtitles', 'Bilingual', 'zh');
      trackRef.current.mode = 'showing';
    }

    const track = trackRef.current;

    while (track.cues && track.cues.length > 0) {
      track.removeCue(track.cues[0]);
    }

    for (const entry of entries) {
      const startSec = srtTimeToSeconds(entry.startTime);
      const endSec = srtTimeToSeconds(entry.endTime);
      if (!Number.isFinite(startSec) || !Number.isFinite(endSec)) continue;
      const text = entry.original ? `${entry.translated}\n${entry.original}` : entry.translated;
      track.addCue(new VTTCue(startSec, endSec, text));
    }
  }, [entries]);

  const hasEdits = useMemo(() => {
    if (entries.length !== originalEntries.length) return true;
    return entries.some(
      (entry, i) =>
        entry.translated !== originalEntries[i].translated ||
        entry.startTime !== originalEntries[i].startTime ||
        entry.endTime !== originalEntries[i].endTime
    );
  }, [entries, originalEntries]);

  const handleTranslatedChange = useCallback((index: number, value: string) => {
    setEntries(prev =>
      prev.map((entry, i) => (i === index ? { ...entry, translated: value } : entry))
    );
  }, []);

  const handleTimeChange = useCallback(
    (index: number, field: 'startTime' | 'endTime', value: string) => {
      setEntries(prev =>
        prev.map((entry, i) => (i === index ? { ...entry, [field]: value } : entry))
      );
    },
    []
  );

  const handleTimeBlur = useCallback(
    (index: number, field: 'startTime' | 'endTime') => {
      setEntries(prev =>
        prev.map((entry, i) => {
          if (i !== index) return entry;
          if (isValidSrtTime(entry[field])) return entry;
          const original = originalEntries[i];
          if (!original) return entry;
          return { ...entry, [field]: original[field] };
        })
      );
    },
    [originalEntries]
  );

  const handleDelete = useCallback((index: number) => {
    setEntries(prev =>
      prev.filter((_, i) => i !== index).map((entry, i) => ({ ...entry, index: i + 1 }))
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
    <div className="space-y-8">
      <style>{`
        video::cue {
          color: #FFFF00;
          background-color: transparent;
          font-family: Arial, sans-serif;
          text-shadow:
            -1px -1px 0 #000, 1px -1px 0 #000,
            -1px 1px 0 #000, 1px 1px 0 #000,
            0 -1px 0 #000, 0 1px 0 #000,
            -1px 0 0 #000, 1px 0 0 #000;
        }
      `}</style>

      {/* Title bar */}
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
          <button
            onClick={() => onBurn(serializeSrt(entries))}
            disabled={isBurning}
            className="text-sm uppercase tracking-widest bg-black text-white px-4 py-2 rounded hover:bg-gray-800 disabled:opacity-50 transition-colors"
          >
            {isBurning ? t('editor.burning') : t('editor.burn')}
          </button>
        </div>
      </div>

      {/* Side-by-side layout */}
      <div className="flex flex-col lg:flex-row gap-8">
        {/* Left: video player (sticky) */}
        <div className="w-full lg:w-5/12">
          <div className="lg:sticky lg:top-8 space-y-2">
            <video
              ref={videoRef}
              controls
              src={videoUrl}
              onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime ?? 0)}
              className="w-full rounded-lg"
            />
            <p className="text-xs text-gray-400 text-center">{t('editor.videoHint')}</p>
          </div>
        </div>

        {/* Right: subtitle entries */}
        <div className="w-full lg:w-7/12 space-y-6">
          {entries.map((entry, i) => (
            <div
              key={`${entry.index}-${i}`}
              onClick={() => handleEntryClick(entry)}
              className={`relative group cursor-pointer pl-3 pr-2 py-3 rounded-lg transition-colors hover:bg-gray-50 ${
                i === activeEntryIndex
                  ? 'border-l-4 border-yellow-400'
                  : 'border-l-4 border-transparent'
              }`}
            >
              {/* Delete button — top-right, visible on hover */}
              <button
                onClick={e => {
                  e.stopPropagation();
                  handleDelete(i);
                }}
                title={t('editor.deleteEntry')}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition-all"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>

              {/* Entry number + time inputs */}
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs font-bold text-gray-300 group-hover:text-black transition-colors">
                  #{entry.index}
                </span>
                <input
                  type="text"
                  value={entry.startTime}
                  onChange={e => handleTimeChange(i, 'startTime', e.target.value)}
                  onBlur={() => handleTimeBlur(i, 'startTime')}
                  onClick={e => e.stopPropagation()}
                  className="font-mono text-xs text-gray-400 bg-transparent border-b border-transparent hover:border-gray-300 focus:border-black focus:outline-none transition-colors w-28 py-0.5"
                />
                <span className="text-xs text-gray-300">→</span>
                <input
                  type="text"
                  value={entry.endTime}
                  onChange={e => handleTimeChange(i, 'endTime', e.target.value)}
                  onBlur={() => handleTimeBlur(i, 'endTime')}
                  onClick={e => e.stopPropagation()}
                  className="font-mono text-xs text-gray-400 bg-transparent border-b border-transparent hover:border-gray-300 focus:border-black focus:outline-none transition-colors w-28 py-0.5"
                />
              </div>

              {/* Translated text (editable) */}
              <textarea
                value={entry.translated}
                onChange={e => handleTranslatedChange(i, e.target.value)}
                onClick={e => e.stopPropagation()}
                rows={Math.max(1, Math.ceil(entry.translated.length / 50))}
                className="w-full bg-transparent text-lg font-serif text-black placeholder-gray-300 focus:outline-none focus:bg-gray-50 p-1 -ml-1 rounded transition-colors resize-none leading-relaxed"
              />

              {/* Original text (read-only) */}
              {entry.original && (
                <p className="text-sm text-gray-400 font-sans leading-relaxed mt-1">
                  {entry.original}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Unsaved hint */}
      {hasEdits && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-black text-white px-6 py-3 rounded-full shadow-2xl animate-bounce">
          <span className="text-sm font-medium">{t('editor.unsavedHint')}</span>
        </div>
      )}
    </div>
  );
}
