import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileType } from '../constants';
import { apiClient } from '../api/client';
import { DisclaimerDialog } from './DisclaimerDialog';
import { triggerDownload } from '../utils/download';

interface DownloadLinksProps {
  jobId: string;
  showVideo?: boolean;
}

const FILE_OPTIONS = [
  { type: FileType.SRT, labelKey: 'download.srt' },
  { type: FileType.ASS, labelKey: 'download.ass' },
  { type: FileType.VIDEO, labelKey: 'download.video' },
] as const;

export function DownloadLinks({ jobId, showVideo }: DownloadLinksProps) {
  const { t } = useTranslation();
  const [pendingUrl, setPendingUrl] = useState<string | null>(null);

  const visibleOptions =
    showVideo === false ? FILE_OPTIONS.filter(opt => opt.type !== FileType.VIDEO) : FILE_OPTIONS;

  return (
    <>
      <div className="space-y-2">
        {visibleOptions.map(({ type, labelKey }) => {
          const url = apiClient.getDownloadUrl(jobId, type);
          return (
            <a
              key={type}
              href={url}
              onClick={e => {
                e.preventDefault();
                setPendingUrl(url);
              }}
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
          );
        })}
      </div>
      <DisclaimerDialog
        open={pendingUrl !== null}
        onConfirm={() => {
          if (pendingUrl) triggerDownload(pendingUrl);
          setPendingUrl(null);
        }}
        onCancel={() => setPendingUrl(null)}
      />
    </>
  );
}
