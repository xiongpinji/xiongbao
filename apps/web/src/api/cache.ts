/**
 * 轻量级 API 请求缓存层。
 *
 * 特性：
 * - TTL 过期自动失效
 * - 相同 key 并发去重（避免重复请求）
 * - 手动失效 / 全量清空
 * - 零依赖，不引入 React Query
 *
 * 用法：
 *   const data = await cachedGet("/agents/roles", { ttl: 60_000 });
 *   invalidateCache("/agents/roles");  // 写操作后失效
 */

interface CacheEntry<T = unknown> {
  data: T;
  expiresAt: number;
}

const store = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<unknown>>();

const DEFAULT_TTL = 30_000; // 30s

/**
 * 带缓存的 GET 请求。
 * @param key 缓存键（通常为 URL path）
 * @param fetcher 实际请求函数
 * @param opts.ttl 缓存有效期 ms
 */
export async function cachedGet<T>(
  key: string,
  fetcher: () => Promise<T>,
  opts?: { ttl?: number }
): Promise<T> {
  const ttl = opts?.ttl ?? DEFAULT_TTL;

  // 命中缓存
  const hit = store.get(key);
  if (hit && Date.now() < hit.expiresAt) {
    return hit.data as T;
  }

  // 并发去重
  const pending = inflight.get(key);
  if (pending) return pending as Promise<T>;

  const promise = fetcher()
    .then((data) => {
      store.set(key, { data, expiresAt: Date.now() + ttl });
      inflight.delete(key);
      return data;
    })
    .catch((err) => {
      inflight.delete(key);
      throw err;
    });

  inflight.set(key, promise);
  return promise;
}

/** 失效指定 key */
export function invalidateCache(key: string): void {
  store.delete(key);
}

/** 失效匹配前缀的所有 key */
export function invalidatePrefix(prefix: string): void {
  for (const k of store.keys()) {
    if (k.startsWith(prefix)) store.delete(k);
  }
}

/** 清空全部缓存 */
export function clearCache(): void {
  store.clear();
}

/** 缓存统计（调试用） */
export function cacheStats(): { size: number; keys: string[] } {
  return { size: store.size, keys: [...store.keys()] };
}
