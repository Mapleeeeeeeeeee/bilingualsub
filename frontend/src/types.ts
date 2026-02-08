import type { FileType, JobStatus } from './constants';

export interface JobCreateRequest {
  youtube_url: string;
  source_lang?: string;
  target_lang?: string;
}

export interface JobCreateResponse {
  job_id: string;
}

export interface ErrorDetail {
  code: string;
  message: string;
  detail?: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  error: ErrorDetail | null;
  output_files: Partial<Record<FileType, string>>;
}

export interface SSEProgressData {
  status: JobStatus;
  progress: number;
  current_step: string | null;
  message: string | null;
}

export interface SSEHandlers {
  onProgress: (data: SSEProgressData) => void;
  onComplete: (data: SSEProgressData) => void;
  onError: (data: { code: string; message: string; detail?: string }) => void;
}
