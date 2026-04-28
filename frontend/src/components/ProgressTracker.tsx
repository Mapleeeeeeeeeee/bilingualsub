import { useTranslation } from 'react-i18next';
import { PIPELINE_STEPS, SubtitleSource, type JobStatus } from '../constants';

interface ProgressTrackerProps {
  status: JobStatus | null;
  progress: number;
  currentStep: string | null;
  subtitleSource?: string;
  steps?: readonly JobStatus[];
}

export function ProgressTracker({
  status,
  progress,
  subtitleSource,
  steps = PIPELINE_STEPS,
}: ProgressTrackerProps) {
  const { t } = useTranslation();

  if (!status) return null;

  const currentStepIndex = steps.indexOf(status);

  return (
    <div className="space-y-8 max-w-md mx-auto">
      {/* Step indicators (Minimal) */}
      <div className="flex justify-between items-center px-4">
        {steps.map((step, index) => {
          const isActive = index === currentStepIndex;
          const isCompleted = index < currentStepIndex;

          return (
            <div key={step} className="flex flex-col items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full transition-all duration-500 ${isActive ? 'bg-black scale-125' : isCompleted ? 'bg-gray-300' : 'bg-gray-100'}`}
              />
              {isActive && (
                <span className="absolute mt-6 text-xs font-serif uppercase tracking-widest animate-fade-in-up">
                  {t(`progress.${step}`)}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-gray-100 h-px">
        <div
          className="h-px bg-black transition-all duration-1000 ease-linear"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Subtitle source badge */}
      {subtitleSource && (
        <p className="text-center text-xs text-gray-400 tracking-wide">
          {t('progress.subtitleSource')}
          {': '}
          {subtitleSource === SubtitleSource.YOUTUBE_MANUAL
            ? t('progress.subtitleSourceYoutube')
            : subtitleSource === SubtitleSource.VISUAL_DESCRIPTION
              ? t('progress.subtitleSourceVisual')
              : t('progress.subtitleSourceWhisper')}
        </p>
      )}
    </div>
  );
}
