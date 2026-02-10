import { useTranslation } from 'react-i18next';

interface DisclaimerDialogProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DisclaimerDialog({ open, onConfirm, onCancel }: DisclaimerDialogProps) {
  const { t } = useTranslation();

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onCancel} />

      {/* Dialog */}
      <div className="relative bg-white rounded-2xl shadow-2xl max-w-md w-full mx-4 p-8 space-y-6">
        <h3 className="text-xl font-serif">{t('disclaimer.title')}</h3>

        <div className="space-y-4 text-sm text-gray-600 leading-relaxed">
          <p>{t('disclaimer.tool_desc')}</p>
          <div className="border-l-2 border-gray-200 pl-4">
            <p className="font-medium text-gray-800">{t('disclaimer.copyright_title')}</p>
            <p className="mt-1">{t('disclaimer.copyright_desc')}</p>
          </div>
        </div>

        <div className="flex gap-3 justify-end pt-2">
          <button
            onClick={onCancel}
            className="px-5 py-2 text-sm text-gray-500 hover:text-black transition-colors"
          >
            {t('disclaimer.cancel')}
          </button>
          <button
            onClick={onConfirm}
            className="px-5 py-2 text-sm bg-black text-white rounded-full hover:bg-gray-800 transition-colors"
          >
            {t('disclaimer.confirm')}
          </button>
        </div>
      </div>
    </div>
  );
}
