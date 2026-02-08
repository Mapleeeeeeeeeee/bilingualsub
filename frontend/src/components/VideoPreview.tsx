import { useTranslation } from 'react-i18next';
import { FileType } from '../constants';
import { apiClient } from '../api/client';

interface VideoPreviewProps {
  jobId: string;
}

export function VideoPreview({ jobId }: VideoPreviewProps) {
  const { t } = useTranslation();

  return (
    <video
      controls
      className="w-full h-full object-cover"
      src={apiClient.getDownloadUrl(jobId, FileType.VIDEO)}
    >
      {t('preview.unsupported')}
    </video>
  );
}
