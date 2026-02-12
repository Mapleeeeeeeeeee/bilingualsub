import { useTranslation } from 'react-i18next';
import { type FileType as FileTypeType, FileType } from '../constants';
import { apiClient } from '../api/client';

interface VideoPreviewProps {
  jobId: string;
  fileType?: FileTypeType;
}

export function VideoPreview({ jobId, fileType = FileType.VIDEO }: VideoPreviewProps) {
  const { t } = useTranslation();

  return (
    <video
      controls
      className="w-full h-full object-cover"
      src={apiClient.getDownloadUrl(jobId, fileType)}
    >
      {t('preview.unsupported')}
    </video>
  );
}
