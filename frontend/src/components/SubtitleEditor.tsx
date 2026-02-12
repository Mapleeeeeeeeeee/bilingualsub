import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/api/client';
import { FileType } from '@/constants';
import { parseSrt, serializeSrt, srtTimeToSeconds, isValidSrtTime } from '@/utils/srt';
import { triggerDownload } from '@/utils/download';
import type { SrtEntry } from '@/types';

interface SubtitleEditorProps {
  jobId: string;
  onBurn: (srtContent: string) => void;
  isBurning: boolean;
}

interface RetranslatePreviewItem {
  index: number;
  original: string;
  before: string;
  after: string;
}

type RetranslateChoice = 'before' | 'after';

export function SubtitleEditor({ jobId, onBurn, isBurning }: SubtitleEditorProps) {
  const { t } = useTranslation();
  const [originalEntries, setOriginalEntries] = useState<SrtEntry[]>([]);
  const [entries, setEntries] = useState<SrtEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [retranslateContext, setRetranslateContext] = useState('');
  const [isRetranslating, setIsRetranslating] = useState(false);
  const [retranslateError, setRetranslateError] = useState<string | null>(null);
  const [retranslatePreview, setRetranslatePreview] = useState<RetranslatePreviewItem[]>([]);
  const [retranslateChoices, setRetranslateChoices] = useState<Record<number, RetranslateChoice>>(
    {}
  );
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
        setSelectedIndices(new Set());
        setRetranslateContext('');
        setRetranslateError(null);
        setRetranslatePreview([]);
        setRetranslateChoices({});
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

  const selectedCount = useMemo(() => selectedIndices.size, [selectedIndices]);

  const handleTranslatedChange = useCallback((index: number, value: string) => {
    setRetranslatePreview([]);
    setRetranslateChoices({});
    setEntries(prev =>
      prev.map((entry, i) => (i === index ? { ...entry, translated: value } : entry))
    );
  }, []);

  const handleTimeChange = useCallback(
    (index: number, field: 'startTime' | 'endTime', value: string) => {
      setRetranslatePreview([]);
      setRetranslateChoices({});
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
    setRetranslatePreview([]);
    setRetranslateChoices({});
    setEntries(prev => {
      const deleted = prev[index];
      const nextEntries = prev
        .filter((_, i) => i !== index)
        .map((entry, i) => ({ ...entry, index: i + 1 }));

      if (deleted) {
        setSelectedIndices(prevSelected => {
          const nextSelected = new Set<number>();
          for (const selectedIndex of prevSelected) {
            if (selectedIndex === deleted.index) continue;
            nextSelected.add(selectedIndex > deleted.index ? selectedIndex - 1 : selectedIndex);
          }
          return nextSelected;
        });
      }

      return nextEntries;
    });
  }, []);

  const handleReset = useCallback(() => {
    setEntries(originalEntries);
    setSelectedIndices(new Set());
    setRetranslateContext('');
    setRetranslateError(null);
    setRetranslatePreview([]);
    setRetranslateChoices({});
  }, [originalEntries]);

  const handleToggleSelect = useCallback((entryIndex: number) => {
    setRetranslatePreview([]);
    setRetranslateChoices({});
    setSelectedIndices(prev => {
      const next = new Set(prev);
      if (next.has(entryIndex)) {
        next.delete(entryIndex);
      } else {
        next.add(entryIndex);
      }
      return next;
    });
  }, []);

  const handleDownload = useCallback(() => {
    const content = serializeSrt(entries);
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    triggerDownload(url, 'bilingualsub-edited.srt');
    URL.revokeObjectURL(url);
  }, [entries]);

  const handlePartialRetranslate = useCallback(async () => {
    if (selectedIndices.size === 0 || isRetranslating || retranslatePreview.length > 0) return;
    setIsRetranslating(true);
    setRetranslateError(null);

    try {
      const response = await apiClient.partialRetranslate(jobId, {
        selected_indices: Array.from(selectedIndices).sort((a, b) => a - b),
        entries: entries.map(entry => ({
          index: entry.index,
          original: entry.original,
          translated: entry.translated,
        })),
        user_context: retranslateContext.trim() || undefined,
      });

      const translatedMap = new Map(
        response.results.map(item => [item.index, item.translated] as const)
      );
      const previewItems = entries
        .filter(entry => translatedMap.has(entry.index))
        .map(entry => ({
          index: entry.index,
          original: entry.original,
          before: entry.translated,
          after: translatedMap.get(entry.index) ?? entry.translated,
        }))
        .sort((a, b) => a.index - b.index);

      if (previewItems.length === 0) {
        setRetranslateError(t('editor.retranslateFailed'));
      } else {
        setRetranslatePreview(previewItems);
        setRetranslateChoices(
          previewItems.reduce<Record<number, RetranslateChoice>>((acc, item) => {
            acc[item.index] = 'after';
            return acc;
          }, {})
        );
      }
    } catch (err) {
      setRetranslateError(err instanceof Error ? err.message : t('editor.retranslateFailed'));
    } finally {
      setIsRetranslating(false);
    }
  }, [
    entries,
    isRetranslating,
    jobId,
    retranslateContext,
    retranslatePreview.length,
    selectedIndices,
    t,
  ]);

  const handleApplyRetranslatePreview = useCallback(() => {
    const translatedMap = new Map(
      retranslatePreview.map(item => {
        const choice = retranslateChoices[item.index] ?? 'after';
        return [item.index, choice === 'before' ? item.before : item.after] as const;
      })
    );
    setEntries(prev =>
      prev.map(entry =>
        translatedMap.has(entry.index)
          ? { ...entry, translated: translatedMap.get(entry.index) ?? entry.translated }
          : entry
      )
    );
    setSelectedIndices(new Set());
    setRetranslatePreview([]);
    setRetranslateChoices({});
  }, [retranslateChoices, retranslatePreview]);

  const handleDiscardRetranslatePreview = useCallback(() => {
    setRetranslatePreview([]);
    setRetranslateChoices({});
  }, []);

  const handleChoiceChange = useCallback((index: number, choice: RetranslateChoice) => {
    setRetranslateChoices(prev => ({ ...prev, [index]: choice }));
  }, []);

  const handleChooseAllBefore = useCallback(() => {
    setRetranslateChoices(
      retranslatePreview.reduce<Record<number, RetranslateChoice>>((acc, item) => {
        acc[item.index] = 'before';
        return acc;
      }, {})
    );
  }, [retranslatePreview]);

  const handleChooseAllAfter = useCallback(() => {
    setRetranslateChoices(
      retranslatePreview.reduce<Record<number, RetranslateChoice>>((acc, item) => {
        acc[item.index] = 'after';
        return acc;
      }, {})
    );
  }, [retranslatePreview]);

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
      <div className="border-b border-black pb-4 space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <h3 className="text-2xl font-serif">{t('editor.title')}</h3>
          <div className="flex flex-wrap items-center gap-4">
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
              onClick={handlePartialRetranslate}
              disabled={selectedCount === 0 || isRetranslating || retranslatePreview.length > 0}
              className="text-sm uppercase tracking-widest border border-black px-4 py-2 rounded hover:bg-black hover:text-white disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-black transition-colors"
            >
              {isRetranslating ? t('editor.retranslating') : t('editor.retranslate')}
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

        <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-3">
          <p className="text-xs text-gray-500 self-center">
            {t('editor.retranslateHint', { count: selectedCount })}
          </p>
          <input
            type="text"
            value={retranslateContext}
            onChange={e => setRetranslateContext(e.target.value)}
            placeholder={t('editor.retranslateContextPlaceholder')}
            className="text-sm border border-gray-300 rounded px-3 py-2 focus:outline-none focus:border-black"
          />
        </div>
        {retranslateError && <p className="text-sm text-red-500">{retranslateError}</p>}

        {retranslatePreview.length > 0 && (
          <div className="border border-gray-100 rounded-2xl p-5 space-y-5 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs uppercase tracking-widest text-black font-semibold">
                {t('editor.retranslatePreviewTitle', { count: retranslatePreview.length })}
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={handleChooseAllBefore}
                  className="text-[11px] uppercase tracking-widest text-gray-500 hover:text-black transition-colors"
                >
                  {t('editor.retranslatePreviewChooseAllBefore')}
                </button>
                <button
                  onClick={handleChooseAllAfter}
                  className="text-[11px] uppercase tracking-widest text-gray-500 hover:text-black transition-colors"
                >
                  {t('editor.retranslatePreviewChooseAllAfter')}
                </button>
                <button
                  onClick={handleDiscardRetranslatePreview}
                  className="text-[11px] uppercase tracking-widest text-gray-500 hover:text-black transition-colors"
                >
                  {t('editor.retranslatePreviewDiscard')}
                </button>
                <button
                  onClick={handleApplyRetranslatePreview}
                  className="text-[11px] uppercase tracking-widest border border-black px-3 py-1.5 rounded-full hover:bg-black hover:text-white transition-colors"
                >
                  {t('editor.retranslatePreviewApply')}
                </button>
              </div>
            </div>

            <div className="max-h-72 overflow-auto space-y-4">
              {retranslatePreview.map(item => (
                <div
                  key={`preview-${item.index}`}
                  className="border border-gray-100 rounded-xl p-4"
                >
                  <p className="text-xs font-mono text-gray-500 mb-2">#{item.index}</p>
                  {item.original && <p className="text-xs text-gray-400 mb-3">{item.original}</p>}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <button
                      type="button"
                      onClick={() => handleChoiceChange(item.index, 'before')}
                      className={`text-left border rounded-xl p-3 transition-colors ${
                        (retranslateChoices[item.index] ?? 'after') === 'before'
                          ? 'border-black'
                          : 'border-gray-100 hover:border-gray-300'
                      }`}
                    >
                      <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1.5">
                        {t('editor.retranslateBefore')}
                      </p>
                      <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                        {item.before}
                      </p>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleChoiceChange(item.index, 'after')}
                      className={`text-left border rounded-xl p-3 transition-colors ${
                        (retranslateChoices[item.index] ?? 'after') === 'after'
                          ? 'border-black'
                          : 'border-gray-100 hover:border-gray-300'
                      }`}
                    >
                      <p className="text-[10px] uppercase tracking-widest text-gray-400 mb-1.5">
                        {t('editor.retranslateAfter')}
                      </p>
                      <p className="text-sm text-black whitespace-pre-wrap leading-relaxed">
                        {item.after}
                      </p>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
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
                <input
                  type="checkbox"
                  checked={selectedIndices.has(entry.index)}
                  onChange={() => handleToggleSelect(entry.index)}
                  onClick={e => e.stopPropagation()}
                  className="h-4 w-4 border-gray-300 text-black focus:ring-black"
                  title={t('editor.selectForRetranslate')}
                />
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
