export class ApiError extends Error {
  status: number;
  code: string;
  detail?: string;

  constructor(status: number, code: string, message: string, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    try {
      const body = await response.json();
      return new ApiError(
        response.status,
        body.code ?? 'unknown_error',
        body.message ?? response.statusText,
        body.detail
      );
    } catch {
      return new ApiError(response.status, 'unknown_error', response.statusText);
    }
  }
}
