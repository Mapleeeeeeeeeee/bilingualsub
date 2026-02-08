import { useCallback, useReducer, useRef } from 'react';
import { JobStatus } from '../constants';
import type { JobCreateRequest, SSEProgressData } from '../types';
import { apiClient } from '../api/client';

// State type
interface JobState {
  phase: 'idle' | 'submitting' | 'processing' | 'completed' | 'failed';
  jobId: string | null;
  status: JobStatus | null;
  progress: number;
  currentStep: string | null;
  error: { code: string; message: string; detail?: string } | null;
}

// Action types
type JobAction =
  | { type: 'SUBMIT' }
  | { type: 'JOB_CREATED'; jobId: string }
  | { type: 'PROGRESS'; data: SSEProgressData }
  | { type: 'COMPLETE' }
  | { type: 'ERROR'; error: { code: string; message: string; detail?: string } }
  | { type: 'RESET' };

const initialState: JobState = {
  phase: 'idle',
  jobId: null,
  status: null,
  progress: 0,
  currentStep: null,
  error: null,
};

function jobReducer(state: JobState, action: JobAction): JobState {
  switch (action.type) {
    case 'SUBMIT':
      return { ...initialState, phase: 'submitting' };
    case 'JOB_CREATED':
      return { ...state, phase: 'processing', jobId: action.jobId };
    case 'PROGRESS':
      return {
        ...state,
        status: action.data.status,
        progress: action.data.progress,
        currentStep: action.data.current_step,
      };
    case 'COMPLETE':
      return {
        ...state,
        phase: 'completed',
        progress: 100,
        status: JobStatus.COMPLETED,
      };
    case 'ERROR':
      return {
        ...state,
        phase: 'failed',
        error: action.error,
        status: JobStatus.FAILED,
      };
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

export function useJob() {
  const [state, dispatch] = useReducer(jobReducer, initialState);
  const eventSourceRef = useRef<EventSource | null>(null);

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  const submitJob = useCallback(
    async (request: JobCreateRequest) => {
      cleanup();
      dispatch({ type: 'SUBMIT' });

      try {
        const response = await apiClient.createJob(request);
        dispatch({ type: 'JOB_CREATED', jobId: response.job_id });

        // Connect SSE
        eventSourceRef.current = apiClient.connectSSE(response.job_id, {
          onProgress: data => dispatch({ type: 'PROGRESS', data }),
          onComplete: () => {
            dispatch({ type: 'COMPLETE' });
            cleanup();
          },
          onError: error => {
            dispatch({ type: 'ERROR', error });
            cleanup();
          },
        });
      } catch (err) {
        const error =
          err instanceof Error
            ? { code: 'submit_error', message: err.message }
            : { code: 'unknown_error', message: 'An unknown error occurred' };
        dispatch({ type: 'ERROR', error });
      }
    },
    [cleanup]
  );

  const reset = useCallback(() => {
    cleanup();
    dispatch({ type: 'RESET' });
  }, [cleanup]);

  return { state, submitJob, reset };
}
