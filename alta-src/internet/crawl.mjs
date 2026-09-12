import { retrievalStatus } from "./retrieval-status.mjs";

function linkPriority(link, query) {
  if (!query) return 0;
  const terms = [
    ...new Set(query.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []),
  ].filter((term) => term.length >= 3 && /\p{L}/u.test(term));
  const corpus = `${link.url} ${link.text ?? ""}`.toLowerCase();
  return terms.filter((term) => corpus.includes(term)).length;
}

export async function crawlSite(
  service,
  { start, pagesLimit, depthLimit, charsLimit, concurrency, query = "" },
  { signal } = {},
) {
  const queue = [{ url: start.href, depth: 0, priority: 0 }];
  const scheduled = new Set([start.href]);
  const pages = [];
  const failures = [];
  let attempted = 0;
  let used = 0;

  while (queue.length && attempted < pagesLimit && charsLimit - used >= 1_000) {
    signal?.throwIfAborted();
    // Stable sort preserves document order among equal matches. Only retrieved
    // same-origin links are followed; priorities are locators, never Evidence.
    if (query)
      queue.sort((a, b) => b.priority - a.priority || a.depth - b.depth);
    const batchSize = Math.min(
      concurrency,
      pagesLimit - attempted,
      queue.length,
      Math.floor((charsLimit - used) / 1_000),
    );
    const batch = queue.splice(0, batchSize);
    attempted += batch.length;
    const perPageChars = Math.min(
      12_000,
      Math.floor((charsLimit - used) / batch.length),
    );
    const settled = await Promise.allSettled(
      batch.map((current) =>
        service.fetchPage(
          { url: current.url, max_chars: perPageChars },
          { signal },
        ),
      ),
    );

    for (let index = 0; index < settled.length; index += 1) {
      const item = settled[index];
      const current = batch[index];
      if (item.status === "rejected") {
        failures.push({
          url: current.url,
          error: String(item.reason?.message ?? item.reason).slice(0, 1_000),
        });
        continue;
      }
      if (used >= charsLimit || pages.length >= pagesLimit) break;
      const page = item.value;
      const available = charsLimit - used;
      const text = page.text.slice(0, available);
      used += text.length;
      pages.push({
        url: page.url,
        title: page.title,
        text,
        metadata: page.metadata,
        reader_used: page.reader_used,
        ...retrievalStatus(page),
        truncated: page.truncated || page.text.length > available,
        ...(page.text.length > available && Number.isInteger(page.text_start)
          ? { text_end: page.text_start + text.length }
          : {}),
      });
      if (current.depth >= depthLimit) continue;
      for (const link of page.links ?? []) {
        let linked;
        try {
          linked = new URL(link.url);
        } catch {
          continue;
        }
        if (linked.origin !== start.origin || scheduled.has(linked.href))
          continue;
        scheduled.add(linked.href);
        queue.push({
          url: linked.href,
          depth: current.depth + 1,
          priority: linkPriority(link, query),
        });
      }
    }
  }

  return {
    start_url: start.href,
    ...(query ? { query } : {}),
    pages,
    failures,
    partial: failures.length > 0,
    ...(pages.some((page) => page.stale) ? { stale: true } : {}),
    attempt_count: attempted,
    page_count: pages.length,
    character_count: used,
    truncated:
      queue.length > 0 || used >= charsLimit || attempted >= pagesLimit,
  };
}
