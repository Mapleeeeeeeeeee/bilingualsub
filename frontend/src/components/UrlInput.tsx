import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { JobCreateRequest } from '../types';

interface UrlInputProps {
  onSubmit: (request: JobCreateRequest) => void;
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
  const [url, setUrl] = useState('');
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('zh-TW');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const youtubePattern = /^https?:\/\/(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)/;
    if (!youtubePattern.test(url)) {
      setError(t('error.invalid_url'));
      return;
    }

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
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <input
          type="url"
          value={url}
          onChange={e => setUrl(e.target.value)}
          placeholder={t('form.url_placeholder')}
          disabled={disabled}
          className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-lg disabled:opacity-50 disabled:cursor-not-allowed"
        />
        {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
      </div>

      <div className="flex gap-4">
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('form.source_lang')}
          </label>
          <select
            value={sourceLang}
            onChange={e => setSourceLang(e.target.value)}
            disabled={disabled}
            className="w-full px-3 py-2 rounded-md border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none disabled:opacity-50"
          >
            {LANGUAGES.map(lang => (
              <option key={lang.value} value={lang.value}>
                {t(lang.labelKey)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('form.target_lang')}
          </label>
          <select
            value={targetLang}
            onChange={e => setTargetLang(e.target.value)}
            disabled={disabled}
            className="w-full px-3 py-2 rounded-md border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none disabled:opacity-50"
          >
            {LANGUAGES.map(lang => (
              <option key={lang.value} value={lang.value}>
                {t(lang.labelKey)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex gap-4">
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('form.startTime')}
          </label>
          <input
            type="text"
            value={startTime}
            onChange={e => setStartTime(e.target.value)}
            placeholder={t('form.timePlaceholder')}
            disabled={disabled}
            className="w-full px-3 py-2 rounded-md border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none disabled:opacity-50"
          />
        </div>
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('form.endTime')}
          </label>
          <input
            type="text"
            value={endTime}
            onChange={e => setEndTime(e.target.value)}
            placeholder={t('form.timePlaceholder')}
            disabled={disabled}
            className="w-full px-3 py-2 rounded-md border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none disabled:opacity-50"
          />
        </div>
      </div>
      <p className="text-xs text-gray-500">{t('form.timeFormatHint')}</p>

      <button
        type="submit"
        disabled={disabled}
        className="w-full py-3 px-6 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {disabled ? t('form.submitting') : t('form.submit')}
      </button>
    </form>
  );
}
