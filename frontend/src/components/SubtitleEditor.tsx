import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/api/client';
import { FileType } from '@/constants';
import { parseSrt, serializeSrt, srtTimeToSeconds } from '@/utils/srt';
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

    // Clear existing cues
    while (track.cues && track.cues.length > 0) {
      track.removeCue(track.cues[0]);
    }

    // Add cues from entries
    for (const entry of entries) {
      const startSec = srtTimeToSeconds(entry.startTime);
      const endSec = srtTimeToSeconds(entry.endTime);
      const text = entry.original ? `${entry.translated}\n${entry.original}` : entry.translated;
      track.addCue(new VTTCue(startSec, endSec, text));
    }
  }, [entries]);

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
          <button
            onClick={() => onBurn(serializeSrt(entries))}
            disabled={isBurning}
            className="text-sm uppercase tracking-widest bg-black text-white px-4 py-2 rounded hover:bg-gray-800 disabled:opacity-50 transition-colors"
          >
            {isBurning ? t('editor.burning') : t('editor.burn')}
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <video
          ref={videoRef}
          controls
          src={videoUrl}
          onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime ?? 0)}
          className="w-full rounded-lg"
        />
        <p className="text-xs text-gray-400 text-center">{t('editor.videoHint')}</p>
      </div>

      <div className="space-y-8">
        {entries.map((entry, i) => (
          <div
            key={entry.index}
            onClick={() => handleEntryClick(entry)}
            className={`grid grid-cols-1 md:grid-cols-12 gap-8 group cursor-pointer pl-3 ${
              i === activeEntryIndex
                ? 'border-l-4 border-yellow-400'
                : 'border-l-4 border-transparent'
            }`}
          >
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
                onClick={e => e.stopPropagation()}
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
