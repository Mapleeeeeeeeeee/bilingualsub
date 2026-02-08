import { useTranslation } from 'react-i18next';
import { PIPELINE_STEPS, JobStatus } from '../constants';

interface ProgressTrackerProps {
  status: JobStatus | null;
  progress: number;
  currentStep: string | null;
}

export function ProgressTracker({ status, progress }: ProgressTrackerProps) {
  const { t } = useTranslation();

  if (!status) return null;

  const currentStepIndex = PIPELINE_STEPS.indexOf(status as (typeof PIPELINE_STEPS)[number]);

  return (
    <div className="space-y-4">
      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-3">
        <div
          className="bg-blue-600 h-3 rounded-full transition-all duration-500"
          style={{ width: `${Math.min(progress, 100)}%` }}
        />
      </div>

      {/* Step indicators */}
      <div className="flex justify-between">
        {PIPELINE_STEPS.map((step, index) => {
          let stepClass = 'text-gray-400';
          if (index < currentStepIndex) {
            stepClass = 'text-green-600';
          } else if (index === currentStepIndex) {
            stepClass = 'text-blue-600 font-semibold';
          }
          return (
            <div key={step} className={`text-xs ${stepClass} text-center flex-1`}>
              {t(`progress.${step}`)}
            </div>
          );
        })}
      </div>

      {/* Status text */}
      <p className="text-center text-sm text-gray-600">
        {status === JobStatus.COMPLETED
          ? t('progress.completed')
          : status === JobStatus.FAILED
            ? t('progress.failed')
            : t(`progress.${status}`)}
      </p>
    </div>
  );
}
