import { FileType } from '../constants';
import type {
  JobCreateRequest,
  JobCreateResponse,
  JobStatusResponse,
  JobUploadRequest,
  PartialRetranslateRequest,
  PartialRetranslateResponse,
  SSEHandlers,
} from '../types';
import { ApiError } from './errors';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = import.meta.env.VITE_API_URL || '') {
    this.baseUrl = baseUrl;
  }

  async createJob(request: JobCreateRequest): Promise<JobCreateResponse> {
    const response = await fetch(`${this.baseUrl}/api/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      throw await ApiError.fromResponse(response);
    }
    return response.json();
  }

  async createJobFromUpload(request: JobUploadRequest): Promise<JobCreateResponse> {
    const formData = new FormData();
    formData.append('file', request.file);
    if (request.source_lang) formData.append('source_lang', request.source_lang);
    if (request.target_lang) formData.append('target_lang', request.target_lang);
    if (request.start_time !== undefined) formData.append('start_time', String(request.start_time));
    if (request.end_time !== undefined) formData.append('end_time', String(request.end_time));

    const response = await fetch(`${this.baseUrl}/api/jobs/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      throw await ApiError.fromResponse(response);
    }
    return response.json();
  }

  async getJobStatus(jobId: string): Promise<JobStatusResponse> {
    const response = await fetch(`${this.baseUrl}/api/jobs/${jobId}`);
    if (!response.ok) {
      throw await ApiError.fromResponse(response);
    }
    return response.json();
  }

  connectSSE(jobId: string, handlers: SSEHandlers): EventSource {
    const es = new EventSource(`${this.baseUrl}/api/jobs/${jobId}/events`);

    es.addEventListener('progress', event => {
      const data = JSON.parse(event.data);
      handlers.onProgress(data);
    });

    es.addEventListener('download_complete', event => {
      const data = JSON.parse(event.data);
      handlers.onDownloadComplete?.(data);
    });

    es.addEventListener('complete', event => {
      const data = JSON.parse(event.data);
      handlers.onComplete(data);
      es.close();
    });

    es.addEventListener('error', event => {
      // Check if this is a server-sent error event with data
      if (event instanceof MessageEvent && event.data) {
        const data = JSON.parse(event.data);
        handlers.onError(data);
      } else {
        handlers.onError({
          code: 'connection_error',
          message: 'SSE connection lost',
        });
      }
      es.close();
    });

    return es;
  }

  async fetchSrtContent(jobId: string): Promise<string> {
    const url = this.getDownloadUrl(jobId, FileType.SRT);
    const response = await fetch(url);
    if (!response.ok) {
      throw await ApiError.fromResponse(response);
    }
    return response.text();
  }

  async startSubtitle(
    jobId: string,
    sourceLang?: string,
    targetLang?: string
  ): Promise<{ status: string }> {
    const payload: { source_lang?: string; target_lang?: string } = {};
    if (sourceLang) payload.source_lang = sourceLang;
    if (targetLang) payload.target_lang = targetLang;

    const response = await fetch(`${this.baseUrl}/api/jobs/${jobId}/subtitle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw await ApiError.fromResponse(response);
    return response.json();
  }

  async burnJob(jobId: string, srtContent: string): Promise<{ status: string }> {
    const response = await fetch(`${this.baseUrl}/api/jobs/${jobId}/burn`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ srt_content: srtContent }),
    });
    if (!response.ok) throw await ApiError.fromResponse(response);
    return response.json();
  }

  async partialRetranslate(
    jobId: string,
    payload: PartialRetranslateRequest
  ): Promise<PartialRetranslateResponse> {
    const response = await fetch(`${this.baseUrl}/api/jobs/${jobId}/retranslate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw await ApiError.fromResponse(response);
    return response.json();
  }

  getDownloadUrl(jobId: string, fileType: FileType): string {
    return `${this.baseUrl}/api/jobs/${jobId}/download/${fileType}`;
  }
}

export const apiClient = new ApiClient();
