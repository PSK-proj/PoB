export function joinUrl(base: string, path: string): string {
  const b = base.replace(/\/+$/, '');
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${b}${p}`;
}

export function wsUrlFromWindow(path: string): string {
  const proto = globalThis.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = globalThis.location.host;
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${proto}//${host}${p}`;
}
