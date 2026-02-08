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
    <div className="space-y-8 max-w-md mx-auto">
      {/* Step indicators (Minimal) */}
      <div className="flex justify-between items-center px-4">
        {PIPELINE_STEPS.map((step, index) => {
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
    </div>
  );
}
