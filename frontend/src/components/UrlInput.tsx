import { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { JobCreateRequest, JobUploadRequest } from '../types';

interface UrlInputProps {
  onSubmit: (request: JobCreateRequest | JobUploadRequest) => void;
  disabled: boolean;
}

type TimeParts = {
  hours: string;
  minutes: string;
  seconds: string;
};

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => i.toString().padStart(2, '0'));
const MINUTE_SECOND_OPTIONS = Array.from({ length: 60 }, (_, i) => i.toString().padStart(2, '0'));

function toSeconds(time: TimeParts): number {
  return (
    parseInt(time.hours, 10) * 3600 + parseInt(time.minutes, 10) * 60 + parseInt(time.seconds, 10)
  );
}

export function UrlInput({ onSubmit, disabled }: UrlInputProps) {
  const { t } = useTranslation();
  const [inputMode, setInputMode] = useState<'url' | 'file'>('url');
  const [url, setUrl] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [rangeEnabled, setRangeEnabled] = useState(false);
  const [startTime, setStartTime] = useState<TimeParts>({
    hours: '00',
    minutes: '00',
    seconds: '00',
  });
  const [endTime, setEndTime] = useState<TimeParts>({
    hours: '00',
    minutes: '01',
    seconds: '00',
  });
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const startSeconds = rangeEnabled ? toSeconds(startTime) : undefined;
    const endSeconds = rangeEnabled ? toSeconds(endTime) : undefined;

    if (
      rangeEnabled &&
      startSeconds !== undefined &&
      endSeconds !== undefined &&
      startSeconds >= endSeconds
    ) {
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

      <div className="flex flex-col items-center gap-4 text-gray-400">
        <div className="flex items-center gap-4">
          <label className="text-xs uppercase tracking-widest font-bold">
            {t('form.label_range')}
          </label>
          <button
            type="button"
            onClick={() => setRangeEnabled(prev => !prev)}
            className="text-xs uppercase tracking-widest border border-gray-300 rounded-full px-3 py-1 hover:border-black hover:text-black transition-colors"
          >
            {rangeEnabled ? t('form.disable_range') : t('form.enable_range')}
          </button>
        </div>

        {rangeEnabled && (
          <div className="flex flex-wrap items-center justify-center gap-6 text-black">
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-widest text-gray-500">
                {t('form.startTime')}
              </span>
              <div className="flex items-center gap-1 border-b border-gray-200 pb-1">
                <select
                  value={startTime.hours}
                  onChange={e => setStartTime(prev => ({ ...prev, hours: e.target.value }))}
                  className="bg-transparent font-mono text-lg focus:outline-none cursor-pointer appearance-none"
                >
                  {HOUR_OPTIONS.map(value => (
                    <option key={`start-h-${value}`} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <span>:</span>
                <select
                  value={startTime.minutes}
                  onChange={e => setStartTime(prev => ({ ...prev, minutes: e.target.value }))}
                  className="bg-transparent font-mono text-lg focus:outline-none cursor-pointer appearance-none"
                >
                  {MINUTE_SECOND_OPTIONS.map(value => (
                    <option key={`start-m-${value}`} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <span>:</span>
                <select
                  value={startTime.seconds}
                  onChange={e => setStartTime(prev => ({ ...prev, seconds: e.target.value }))}
                  className="bg-transparent font-mono text-lg focus:outline-none cursor-pointer appearance-none"
                >
                  {MINUTE_SECOND_OPTIONS.map(value => (
                    <option key={`start-s-${value}`} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <span className="text-gray-300">→</span>

            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-widest text-gray-500">
                {t('form.endTime')}
              </span>
              <div className="flex items-center gap-1 border-b border-gray-200 pb-1">
                <select
                  value={endTime.hours}
                  onChange={e => setEndTime(prev => ({ ...prev, hours: e.target.value }))}
                  className="bg-transparent font-mono text-lg focus:outline-none cursor-pointer appearance-none"
                >
                  {HOUR_OPTIONS.map(value => (
                    <option key={`end-h-${value}`} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <span>:</span>
                <select
                  value={endTime.minutes}
                  onChange={e => setEndTime(prev => ({ ...prev, minutes: e.target.value }))}
                  className="bg-transparent font-mono text-lg focus:outline-none cursor-pointer appearance-none"
                >
                  {MINUTE_SECOND_OPTIONS.map(value => (
                    <option key={`end-m-${value}`} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <span>:</span>
                <select
                  value={endTime.seconds}
                  onChange={e => setEndTime(prev => ({ ...prev, seconds: e.target.value }))}
                  className="bg-transparent font-mono text-lg focus:outline-none cursor-pointer appearance-none"
                >
                  {MINUTE_SECOND_OPTIONS.map(value => (
                    <option key={`end-s-${value}`} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                setStartTime({ hours: '00', minutes: '00', seconds: '00' });
                setEndTime({ hours: '00', minutes: '01', seconds: '00' });
              }}
              className="text-xs text-gray-400 hover:text-black transition-colors"
            >
              {t('form.clear_range')}
            </button>
          </div>
        )}
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
