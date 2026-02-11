import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './components/LanguageSwitcher';
import { UrlInput } from './components/UrlInput';
import { ProgressTracker } from './components/ProgressTracker';
import { DownloadLinks } from './components/DownloadLinks';
import { VideoPreview } from './components/VideoPreview';
import { SubtitleEditor } from './components/SubtitleEditor';
import { useJob } from './hooks/useJob';
import { SUBTITLE_STEPS, FileType } from './constants';
import { apiClient } from './api/client';

function App() {
  const { t } = useTranslation();
  const { state, submitJob, subtitleJob, burnJob, reset, backToEdit } = useJob();

  const isIdle = state.phase === 'idle';
  const isProcessing = state.phase === 'submitting' || state.phase === 'processing';
  const isDownloadComplete = state.phase === 'download_complete' && state.jobId;
  const isSubtitling = state.phase === 'subtitling';
  const isCompleted = state.phase === 'completed' && state.jobId;
  const isBurning = state.phase === 'burning';
  const isBurned = state.phase === 'burned' && state.jobId;
  const isFailed = state.phase === 'failed';

  return (
    <div className="min-h-screen bg-white text-black selection:bg-black selection:text-white font-sans flex flex-col">
      {/* Minimal Header */}
      <header className="fixed top-0 right-0 p-8 z-50">
        <LanguageSwitcher />
      </header>

      <main className="flex-1 w-full max-w-7xl mx-auto px-6 py-12 flex flex-col justify-center min-h-screen transition-all duration-700 ease-in-out">
        {/* IDLE STATE: Hero Input */}
        {isIdle && (
          <div className="max-w-2xl mx-auto w-full space-y-12 animate-fade-in-up">
            <div className="text-center space-y-4">
              <h1 className="text-6xl font-serif font-light tracking-tight text-black">
                {t('app.title')}
              </h1>
              <p className="text-xl text-gray-400 font-light">{t('app.subtitle')}</p>
            </div>
            <UrlInput onSubmit={submitJob} disabled={false} />
          </div>
        )}

        {/* PROCESSING STATE: Minimal Progress */}
        {isProcessing && (
          <div className="max-w-xl mx-auto w-full space-y-12 text-center animate-fade-in-up">
            <div className="space-y-4">
              <h2 className="text-3xl font-serif font-light">{t('app.processing_title')}</h2>
              <p className="text-gray-400">{t('app.processing_desc')}</p>
            </div>
            <ProgressTracker
              status={state.status}
              progress={state.progress}
              currentStep={state.currentStep}
            />
          </div>
        )}

        {/* DOWNLOAD COMPLETE STATE: Preview + Generate Subtitles */}
        {isDownloadComplete && (
          <div className="max-w-2xl mx-auto w-full space-y-12 animate-fade-in-up">
            <div className="text-center space-y-4">
              <h2 className="text-3xl font-serif font-light">{t('app.download_complete_title')}</h2>
              <p className="text-gray-400">{t('app.download_complete_desc')}</p>
            </div>

            {/* Video Preview */}
            <div className="rounded-2xl overflow-hidden shadow-lg shadow-gray-200 bg-black">
              <VideoPreview jobId={state.jobId!} fileType={FileType.SOURCE_VIDEO} />
            </div>

            {/* Actions */}
            <div className="flex flex-col items-center gap-4">
              <button
                onClick={subtitleJob}
                className="px-8 py-3 bg-black text-white rounded-full hover:scale-105 transition-transform"
              >
                {t('app.generate_subtitles')}
              </button>
              <div className="flex items-center gap-6">
                <a
                  href={apiClient.getDownloadUrl(state.jobId!, FileType.SOURCE_VIDEO)}
                  download
                  className="text-sm text-gray-400 hover:text-black transition-colors"
                >
                  {t('app.download_original_video')}
                </a>
                <a
                  href={apiClient.getDownloadUrl(state.jobId!, FileType.AUDIO)}
                  download
                  className="text-sm text-gray-400 hover:text-black transition-colors"
                >
                  {t('app.download_audio')}
                </a>
                <button
                  onClick={reset}
                  className="text-sm text-gray-400 hover:text-black transition-colors"
                >
                  {t('app.start_over')}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* SUBTITLING STATE: Subtitle generation progress */}
        {isSubtitling && (
          <div className="max-w-xl mx-auto w-full space-y-12 text-center animate-fade-in-up">
            <div className="space-y-4">
              <h2 className="text-3xl font-serif font-light">{t('app.processing_title')}</h2>
              <p className="text-gray-400">{t('app.subtitling_desc')}</p>
            </div>
            <ProgressTracker
              status={state.status}
              progress={state.progress}
              currentStep={state.currentStep}
              steps={SUBTITLE_STEPS}
            />
          </div>
        )}

        {/* FAILED STATE */}
        {isFailed && state.error && (
          <div className="max-w-xl mx-auto w-full text-center space-y-8 animate-fade-in-up">
            <h2 className="text-4xl font-serif text-red-600">{t('app.error_title')}</h2>
            <p className="text-gray-500 text-lg">
              {t(`error.${state.error.code}`, { defaultValue: state.error.message })}
            </p>
            {state.error.detail && (
              <p className="text-gray-400 text-sm font-mono">{state.error.detail}</p>
            )}
            <button
              onClick={reset}
              className="px-8 py-3 bg-black text-white rounded-full hover:scale-105 transition-transform"
            >
              {t('form.submit')}
            </button>
          </div>
        )}

        {/* COMPLETED STATE: Preview-first (no burned video yet) */}
        {isCompleted && (
          <div className="w-full space-y-16 animate-fade-in-up py-12">
            {/* Top Bar with Back Button */}
            <div className="flex items-center justify-between">
              <button
                onClick={reset}
                className="flex items-center gap-2 text-gray-400 hover:text-black transition-colors"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M10 19l-7-7m0 0l7-7m-7 7h18"
                  />
                </svg>
                <span className="text-sm font-medium uppercase tracking-widest">
                  {t('app.start_over')}
                </span>
              </button>
              <h1 className="text-2xl font-serif">{t('app.title')}</h1>
              <div className="w-24"></div> {/* Spacer for balance */}
            </div>

            {/* Editor Section */}
            <div className="border-t border-gray-100 pt-16">
              <div className="max-w-6xl mx-auto">
                <SubtitleEditor jobId={state.jobId!} onBurn={burnJob} isBurning={false} />
              </div>
            </div>
          </div>
        )}

        {/* BURNING STATE: Burn progress */}
        {isBurning && (
          <div className="max-w-xl mx-auto w-full space-y-12 text-center animate-fade-in-up">
            <div className="space-y-4">
              <h2 className="text-3xl font-serif font-light">{t('app.processing_title')}</h2>
              <p className="text-gray-400">{t('progress.burning')}</p>
            </div>
            <ProgressTracker
              status={state.status}
              progress={state.progress}
              currentStep={state.currentStep}
            />
          </div>
        )}

        {/* BURNED STATE: Video ready + can re-edit */}
        {isBurned && (
          <div className="w-full space-y-16 animate-fade-in-up py-12">
            {/* Top Bar with Back Button */}
            <div className="flex items-center justify-between">
              <button
                onClick={reset}
                className="flex items-center gap-2 text-gray-400 hover:text-black transition-colors"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M10 19l-7-7m0 0l7-7m-7 7h18"
                  />
                </svg>
                <span className="text-sm font-medium uppercase tracking-widest">
                  {t('app.start_over')}
                </span>
              </button>
              <h1 className="text-2xl font-serif">{t('app.title')}</h1>
              <div className="w-24"></div> {/* Spacer for balance */}
            </div>

            {/* Video & Downloads Row */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-12 items-start">
              <div className="lg:col-span-2">
                <div className="rounded-3xl overflow-hidden shadow-2xl shadow-gray-200 bg-black">
                  <VideoPreview jobId={state.jobId!} />
                </div>
              </div>
              <div className="lg:col-span-1 space-y-8">
                <div>
                  <h3 className="text-3xl font-serif mb-6">{t('app.downloads_title')}</h3>
                  <DownloadLinks jobId={state.jobId!} showVideo={true} />
                </div>
                <button
                  onClick={backToEdit}
                  className="flex items-center justify-center gap-2 w-full text-sm text-gray-500 hover:text-black transition-colors py-3 border border-gray-200 hover:border-black rounded-full"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M10 19l-7-7m0 0l7-7m-7 7h18"
                    />
                  </svg>
                  {t('app.back_to_edit')}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
