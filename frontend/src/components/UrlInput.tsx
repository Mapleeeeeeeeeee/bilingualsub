import { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { JobCreateRequest, JobUploadRequest } from '../types';

interface UrlInputProps {
  onSubmit: (request: JobCreateRequest | JobUploadRequest) => void;
  disabled: boolean;
}

const LANGUAGES = [
  { value: 'en', labelKey: 'lang.en' },
  { value: 'zh-TW', labelKey: 'lang.zh-TW' },
  { value: 'ja', labelKey: 'lang.ja' },
  { value: 'ko', labelKey: 'lang.ko' },
];

function isValidTimeFormat(value: string): boolean {
  if (value === '') return true;
  return /^\d{1,2}:\d{2}:\d{2}$/.test(value);
}

function parseTime(value: string): number | undefined {
  if (value === '') return undefined;
  const parts = value.split(':');
  const hours = parseInt(parts[0], 10);
  const minutes = parseInt(parts[1], 10);
  const seconds = parseInt(parts[2], 10);
  return hours * 3600 + minutes * 60 + seconds;
}

export function UrlInput({ onSubmit, disabled }: UrlInputProps) {
  const { t } = useTranslation();
  const [inputMode, setInputMode] = useState<'url' | 'file'>('url');
  const [url, setUrl] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('zh-TW');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!isValidTimeFormat(startTime) || !isValidTimeFormat(endTime)) {
      setError(t('error.invalidTimeFormat'));
      return;
    }

    const startSeconds = parseTime(startTime);
    const endSeconds = parseTime(endTime);

    if (startSeconds !== undefined && endSeconds !== undefined && startSeconds >= endSeconds) {
      setError(t('error.invalidTimeRange'));
      return;
    }

    if (inputMode === 'file') {
      if (!selectedFile) {
        setError(t('form.filePlaceholder'));
        return;
      }
      const request: JobUploadRequest = {
        file: selectedFile,
        source_lang: sourceLang,
        target_lang: targetLang,
      };
      if (startSeconds !== undefined) request.start_time = startSeconds;
      if (endSeconds !== undefined) request.end_time = endSeconds;
      onSubmit(request);
      return;
    }

    const youtubePattern = /^https?:\/\/(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)/;
    if (!youtubePattern.test(url)) {
      setError(t('error.invalid_url'));
      return;
    }

    const request: JobCreateRequest = {
      youtube_url: url,
      source_lang: sourceLang,
      target_lang: targetLang,
    };
    if (startSeconds !== undefined) request.start_time = startSeconds;
    if (endSeconds !== undefined) request.end_time = endSeconds;

    onSubmit(request);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-16">
      <div className="flex justify-center gap-8 mb-4">
        <button
          type="button"
          onClick={() => setInputMode('url')}
          className={`text-xs uppercase tracking-widest font-bold pb-1 border-b-2 transition-colors ${
            inputMode === 'url'
              ? 'border-black text-black'
              : 'border-transparent text-gray-300 hover:text-gray-500'
          }`}
        >
          {t('form.inputModeUrl')}
        </button>
        <button
          type="button"
          onClick={() => setInputMode('file')}
          className={`text-xs uppercase tracking-widest font-bold pb-1 border-b-2 transition-colors ${
            inputMode === 'file'
              ? 'border-black text-black'
              : 'border-transparent text-gray-300 hover:text-gray-500'
          }`}
        >
          {t('form.inputModeFile')}
        </button>
      </div>

      <div className="relative group">
        {inputMode === 'url' ? (
          <input
            type="url"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder={t('form.paste_placeholder')}
            disabled={disabled}
            className="w-full py-6 bg-transparent border-b-2 border-gray-100 text-3xl md:text-5xl font-serif text-black placeholder-gray-200 focus:outline-none focus:border-black transition-colors text-center"
          />
        ) : (
          <div className="flex flex-col items-center gap-4">
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*,audio/*,.mp4,.avi,.mov,.mkv,.mp3,.wav,.m4a,.webm"
              onChange={e => setSelectedFile(e.target.files?.[0] ?? null)}
              disabled={disabled}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className="w-full py-6 bg-transparent border-b-2 border-gray-100 text-3xl md:text-5xl font-serif text-gray-200 hover:border-black focus:outline-none focus:border-black transition-colors text-center"
            >
              {selectedFile
                ? t('form.fileSelected', { filename: selectedFile.name })
                : t('form.filePlaceholder')}
            </button>
          </div>
        )}
        {error && (
          <p className="absolute -bottom-8 left-0 w-full text-center text-red-500 text-sm font-medium">
            {error}
          </p>
        )}
      </div>

      <div className="flex flex-col md:flex-row items-center justify-center gap-12 text-gray-400">
        <div className="flex items-center gap-4">
          <label className="text-xs uppercase tracking-widest font-bold">
            {t('form.label_translate')}
          </label>
          <div className="flex items-center gap-2 text-black font-serif text-xl border-b border-gray-200 pb-1">
            <select
              value={sourceLang}
              onChange={e => setSourceLang(e.target.value)}
              disabled={disabled}
              className="bg-transparent focus:outline-none cursor-pointer appearance-none hover:opacity-60"
            >
              {LANGUAGES.map(lang => (
                <option key={lang.value} value={lang.value}>
                  {t(lang.labelKey)}
                </option>
              ))}
            </select>
            <span className="text-gray-300">→</span>
            <select
              value={targetLang}
              onChange={e => setTargetLang(e.target.value)}
              disabled={disabled}
              className="bg-transparent focus:outline-none cursor-pointer appearance-none hover:opacity-60"
            >
              {LANGUAGES.map(lang => (
                <option key={lang.value} value={lang.value}>
                  {t(lang.labelKey)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <label className="text-xs uppercase tracking-widest font-bold">
            {t('form.label_range')}
          </label>
          <div className="flex items-center gap-2 text-black font-mono text-lg border-b border-gray-200 pb-1">
            <input
              type="text"
              value={startTime}
              onChange={e => setStartTime(e.target.value)}
              placeholder="00:00:00"
              className="w-24 bg-transparent text-center focus:outline-none placeholder-gray-200"
            />
            <span className="text-gray-300">-</span>
            <input
              type="text"
              value={endTime}
              onChange={e => setEndTime(e.target.value)}
              placeholder="00:00:00"
              className="w-24 bg-transparent text-center focus:outline-none placeholder-gray-200"
            />
          </div>
        </div>
      </div>

      <div className="flex justify-center">
        <button
          type="submit"
          disabled={disabled}
          className="px-12 py-5 bg-black text-white text-lg font-medium rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:cursor-not-allowed shadow-2xl shadow-gray-200"
        >
          {disabled ? t('form.submitting') : t('form.start_processing')}
        </button>
      </div>
    </form>
  );
}
