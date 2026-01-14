export interface ApiError {
  status: number;
  message: string;
  url?: string;
  details?: unknown;
}

export class ApiHttpError extends Error {
  override readonly name = 'ApiHttpError';
  constructor(public readonly api: ApiError) {
    super(api.message);
  }
}
export const isApiHttpError = (e: unknown): e is ApiHttpError =>
  e instanceof ApiHttpError;
