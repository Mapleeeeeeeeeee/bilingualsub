import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './components/LanguageSwitcher';
import { UrlInput } from './components/UrlInput';
import { ProgressTracker } from './components/ProgressTracker';
import { DownloadLinks } from './components/DownloadLinks';
import { useJob } from './hooks/useJob';

function App() {
  const { t } = useTranslation();
  const { state, submitJob, reset } = useJob();

  const isProcessing = state.phase === 'submitting' || state.phase === 'processing';

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-2xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{t('app.title')}</h1>
            <p className="text-sm text-gray-500">{t('app.subtitle')}</p>
          </div>
          <LanguageSwitcher />
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-2xl mx-auto px-4 py-8 space-y-8">
        {/* URL Input */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <UrlInput onSubmit={submitJob} disabled={isProcessing} />
        </div>

        {/* Progress */}
        {(state.phase === 'processing' ||
          state.phase === 'completed' ||
          state.phase === 'failed') && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <ProgressTracker
              status={state.status}
              progress={state.progress}
              currentStep={state.currentStep}
            />
          </div>
        )}

        {/* Error */}
        {state.phase === 'failed' && state.error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6">
            <p className="text-red-800 font-medium">
              {t(`error.${state.error.code}`, { defaultValue: state.error.message })}
            </p>
            {state.error.detail && (
              <p className="mt-1 text-sm text-red-600">{state.error.detail}</p>
            )}
            <button
              onClick={reset}
              className="mt-3 px-4 py-2 text-sm bg-red-100 text-red-700 rounded-md hover:bg-red-200 transition-colors"
            >
              {t('form.submit')}
            </button>
          </div>
        )}

        {/* Download links */}
        {state.phase === 'completed' && state.jobId && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <DownloadLinks jobId={state.jobId} />
            <button
              onClick={reset}
              className="mt-4 w-full py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
            >
              {t('form.submit')}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
