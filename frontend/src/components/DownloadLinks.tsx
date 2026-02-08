import { useTranslation } from 'react-i18next';
import { FileType } from '../constants';
import { apiClient } from '../api/client';

interface DownloadLinksProps {
  jobId: string;
}

const FILE_OPTIONS = [
  { type: FileType.SRT, labelKey: 'download.srt' },
  { type: FileType.ASS, labelKey: 'download.ass' },
  { type: FileType.VIDEO, labelKey: 'download.video' },
] as const;

export function DownloadLinks({ jobId }: DownloadLinksProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2">
      {FILE_OPTIONS.map(({ type, labelKey }) => (
        <a
          key={type}
          href={apiClient.getDownloadUrl(jobId, type)}
          download
          className="flex items-center justify-between py-4 border-b border-gray-100 hover:pl-4 transition-all group"
        >
          <span className="text-lg font-light text-gray-900 group-hover:text-black">
            {t(labelKey)}
          </span>
          <svg
            className="w-5 h-5 text-gray-300 group-hover:text-black transition-colors"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1}
              d="M17 8l4 4m0 0l-4 4m4-4H3"
            />
          </svg>
        </a>
      ))}
    </div>
  );
}
