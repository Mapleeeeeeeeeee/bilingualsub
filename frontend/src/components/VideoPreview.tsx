import { useTranslation } from 'react-i18next';
import { FileType } from '../constants';
import { apiClient } from '../api/client';

interface VideoPreviewProps {
  jobId: string;
}

export function VideoPreview({ jobId }: VideoPreviewProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold text-gray-800">{t('preview.title')}</h3>
      <video
        controls
        className="w-full rounded-lg"
        src={apiClient.getDownloadUrl(jobId, FileType.VIDEO)}
      >
        {t('preview.unsupported')}
      </video>
    </div>
  );
}
