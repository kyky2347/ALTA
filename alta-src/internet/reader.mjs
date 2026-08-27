function clean(value) {
  return String(value ?? "")
    .replace(/\r/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function frontmatterValue(body, name) {
  const match = body.match(
    new RegExp(`^${name}:\\s*(?:"([^"]*)"|'([^']*)'|(.+))$`, "im"),
  );
  return clean(match?.[1] ?? match?.[2] ?? match?.[3]);
}

function readerLinks(body, baseUrl, maximum = 100) {
  const links = [];
  const seen = new Set();
  for (const match of body.matchAll(/\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g)) {
    try {
      const url = new URL(match[2], baseUrl);
      url.hash = "";
      if (seen.has(url.href)) continue;
      seen.add(url.href);
      links.push({ url: url.href, text: clean(match[1]).slice(0, 240) });
      if (links.length >= maximum) break;
    } catch {}
  }
  return links;
}

export function readerRequestUrl(baseUrl, targetUrl) {
  const base = String(baseUrl || "https://r.jina.ai").replace(/\/+$/, "");
  return `${base}/${targetUrl}`;
}

export function extractReaderDocument(body, targetUrl) {
  const text = clean(body.replace(/^---\s*\n[\s\S]*?\n---\s*\n?/, ""));
  return {
    kind: "reader-markdown",
    title: frontmatterValue(body, "title"),
    text,
    links: readerLinks(text, targetUrl),
    metadata: {
      description: frontmatterValue(body, "description"),
      source_url: frontmatterValue(body, "url") || targetUrl,
    },
  };
}
