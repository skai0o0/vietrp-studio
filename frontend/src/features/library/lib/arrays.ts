/** Returns a copy of `items` with the element at `from` moved to `to`. Out-of-range moves are no-ops. */
export function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  const next = [...items];
  if (from === to || from < 0 || to < 0 || from >= next.length || to >= next.length) return next;
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved as T);
  return next;
}

export function replaceAt<T>(items: readonly T[], index: number, value: T): T[] {
  return items.map((item, i) => (i === index ? value : item));
}

export function removeAt<T>(items: readonly T[], index: number): T[] {
  return items.filter((_, i) => i !== index);
}

/** `prefix_1`, `prefix_2`, … : the first slug not in `taken`. Slugs match `[a-z0-9_]{1,40}`. */
export function uniqueSlug(prefix: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  let n = used.size + 1;
  while (used.has(`${prefix}_${n}`)) n += 1;
  return `${prefix}_${n}`;
}
