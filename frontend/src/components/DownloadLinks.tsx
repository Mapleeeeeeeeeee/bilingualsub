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
    <div className="space-y-3">
      <h3 className="text-lg font-semibold text-gray-800">{t('download.title')}</h3>
      <div className="flex gap-3">
        {FILE_OPTIONS.map(({ type, labelKey }) => (
          <a
            key={type}
            href={apiClient.getDownloadUrl(jobId, type)}
            download
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
          >
            {t(labelKey)}
          </a>
        ))}
      </div>
    </div>
  );
}
