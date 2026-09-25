// Dünne Hülle um fetch für die CONSTRUCT-API. Wirft ApiError mit der
// Fehlermeldung des Servers ({"error": "..."}), damit Oberflächen sie direkt
// anzeigen können.

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function handle<T>(res: Response): Promise<T> {
  const type = res.headers.get('content-type') ?? ''
  const body: unknown = type.includes('json') ? await res.json() : await res.text()
  if (!res.ok) {
    const msg =
      body && typeof body === 'object' && 'error' in body
        ? String((body as { error: unknown }).error)
        : `${res.status} ${res.statusText}`
    throw new ApiError(msg, res.status)
  }
  return body as T
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  return handle<T>(await fetch(path, init))
}

export async function apiPost<T>(path: string, data?: unknown, init?: RequestInit): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: data === undefined ? undefined : JSON.stringify(data),
      ...init,
    }),
  )
}

export async function apiDelete<T>(path: string): Promise<T> {
  return handle<T>(await fetch(path, { method: 'DELETE' }))
}
