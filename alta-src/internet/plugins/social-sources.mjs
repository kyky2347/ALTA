import { parseFeed } from "./discovery.mjs";

export const DIRECT_SOCIAL_PLATFORMS = new Set([
  "bluesky",
  "hackernews",
  "lemmy",
  "mastodon",
  "reddit",
  "stackexchange",
  "peertube",
  "devto",
  "discourse",
  "youtube",
  "stocktwits",
]);

export function cleanSocial(value, maximum = 1_500) {
  return String(value ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&(?:nbsp|#160);/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maximum);
}

async function bluesky(service, args, options) {
  const url = new URL(
    "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
  );
  url.searchParams.set("q", args.query);
  url.searchParams.set("limit", String(args.maximum));
  url.searchParams.set("sort", args.sort === "latest" ? "latest" : "top");
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "social-bluesky",
      attempts: 1,
    },
    options,
  );
  return (JSON.parse(response.text).posts ?? []).flatMap((post) => {
    const handle = post.author?.handle;
    const recordKey = String(post.uri ?? "")
      .split("/")
      .pop();
    if (!handle || !recordKey) return [];
    return [
      {
        platform: "bluesky",
        url: `https://bsky.app/profile/${handle}/post/${recordKey}`,
        author: post.author?.displayName || handle,
        handle,
        title: cleanSocial(post.record?.text, 280),
        content: cleanSocial(post.record?.text),
        published_at: post.record?.createdAt ?? post.indexedAt ?? "",
        metrics: {
          likes: post.likeCount ?? 0,
          replies: post.replyCount ?? 0,
          reposts: post.repostCount ?? 0,
          quotes: post.quoteCount ?? 0,
        },
        provider: "bluesky-public-appview",
      },
    ];
  });
}

async function hackerNews(service, args, options) {
  const endpoint = args.sort === "latest" ? "search_by_date" : "search";
  const url = new URL(`https://hn.algolia.com/api/v1/${endpoint}`);
  url.searchParams.set("query", args.query);
  url.searchParams.set("tags", "story");
  url.searchParams.set("hitsPerPage", String(args.maximum));
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "social-hackernews",
      attempts: 2,
    },
    options,
  );
  return (JSON.parse(response.text).hits ?? []).map((item) => ({
    platform: "hackernews",
    url: `https://news.ycombinator.com/item?id=${item.objectID}`,
    external_url: item.url ?? "",
    author: item.author ?? "",
    title: cleanSocial(item.title || item.story_title, 500),
    content: cleanSocial(item.story_text || item.comment_text),
    published_at: item.created_at ?? "",
    metrics: {
      points: item.points ?? 0,
      comments: item.num_comments ?? 0,
    },
    provider: "algolia-hackernews",
  }));
}

async function lemmy(service, args, options) {
  const url = new URL("/api/v3/search", service.lemmyUrl);
  url.searchParams.set("q", args.query);
  url.searchParams.set("type_", "Posts");
  url.searchParams.set("sort", args.sort === "latest" ? "New" : "TopAll");
  url.searchParams.set("limit", String(args.maximum));
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "social-lemmy",
      attempts: 2,
    },
    options,
  );
  return (JSON.parse(response.text).posts ?? []).map((view) => ({
    platform: "lemmy",
    url:
      view.post?.ap_id ??
      new URL(`/post/${view.post?.id}`, service.lemmyUrl).href,
    external_url: view.post?.url ?? "",
    author: view.creator?.name ?? "",
    community: view.community?.name ?? "",
    title: cleanSocial(view.post?.name, 500),
    content: cleanSocial(view.post?.body),
    published_at: view.post?.published ?? "",
    metrics: {
      score: view.counts?.score ?? 0,
      comments: view.counts?.comments ?? 0,
    },
    provider: "lemmy-public-api",
  }));
}

async function mastodon(service, args, options) {
  if (!args.hashtag) return [];
  const url = new URL(
    `/api/v1/timelines/tag/${encodeURIComponent(args.hashtag)}`,
    service.mastodonUrl,
  );
  url.searchParams.set("limit", String(args.maximum));
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "social-mastodon",
      attempts: 2,
    },
    options,
  );
  return JSON.parse(response.text).map((status) => ({
    platform: "mastodon",
    url: status.url ?? status.uri,
    author: status.account?.display_name || status.account?.username || "",
    handle: status.account?.acct ?? "",
    title: cleanSocial(status.content, 280),
    content: cleanSocial(status.content),
    published_at: status.created_at ?? "",
    metrics: {
      favourites: status.favourites_count ?? 0,
      replies: status.replies_count ?? 0,
      reblogs: status.reblogs_count ?? 0,
    },
    provider: "mastodon-public-timeline",
  }));
}

async function reddit(service, args, options) {
  const url = new URL("https://www.reddit.com/search.rss");
  url.searchParams.set("q", args.query);
  url.searchParams.set("sort", args.sort === "latest" ? "new" : "relevance");
  url.searchParams.set("t", "all");
  url.searchParams.set("limit", String(args.maximum));
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/atom+xml,application/xml,text/xml",
      max_chars: 512_000,
      cache_namespace: "social-reddit-rss",
      attempts: 1,
    },
    options,
  );
  return parseFeed(response.text, response.url, args.maximum).map((item) => ({
    platform: "reddit",
    url: item.url,
    author: item.author,
    title: item.title,
    content: item.summary,
    published_at: item.published,
    metrics: {},
    provider: "reddit-public-rss",
  }));
}

async function stackExchange(service, args, options) {
  const site = String(args.stackexchangeSite ?? "stackoverflow")
    .trim()
    .toLowerCase();
  if (!/^[a-z0-9.-]{1,60}$/.test(site))
    throw Object.assign(new Error("invalid Stack Exchange site"), {
      status: 400,
      code: "alta_social_invalid_stackexchange_site",
    });
  const url = new URL("https://api.stackexchange.com/2.3/search/advanced");
  url.searchParams.set("site", site);
  url.searchParams.set("q", args.query);
  url.searchParams.set("pagesize", String(args.maximum));
  url.searchParams.set("order", "desc");
  url.searchParams.set(
    "sort",
    args.sort === "latest" ? "creation" : "relevance",
  );
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "social-stackexchange",
      attempts: 1,
    },
    options,
  );
  return (JSON.parse(response.text).items ?? []).map((item) => ({
    platform: "stackexchange",
    url: item.link,
    author: item.owner?.display_name ?? "",
    title: cleanSocial(item.title, 500),
    content: "",
    published_at: new Date((item.creation_date ?? 0) * 1_000).toISOString(),
    tags: (item.tags ?? []).slice(0, 10),
    metrics: {
      score: item.score ?? 0,
      answers: item.answer_count ?? 0,
      views: item.view_count ?? 0,
      accepted: item.is_answered ?? false,
    },
    provider: "stackexchange-public-api",
  }));
}

async function peerTube(service, args, options) {
  const url = new URL("/api/v1/search/videos", service.peertubeUrl);
  url.searchParams.set("search", args.query);
  url.searchParams.set("count", String(args.maximum));
  if (args.sort === "latest") url.searchParams.set("sort", "-publishedAt");
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "social-peertube",
      attempts: 2,
    },
    options,
  );
  return (JSON.parse(response.text).data ?? []).map((item) => ({
    platform: "peertube",
    url:
      item.url ??
      new URL(`/w/${item.shortUUID ?? item.uuid}`, service.peertubeUrl).href,
    author: item.account?.displayName || item.account?.name || "",
    community: item.channel?.displayName || item.channel?.name || "",
    title: cleanSocial(item.name, 500),
    content: cleanSocial(item.description),
    published_at: item.publishedAt ?? item.createdAt ?? "",
    metrics: {
      views: item.views ?? 0,
      likes: item.likes ?? 0,
      dislikes: item.dislikes ?? 0,
    },
    provider: "peertube-public-api",
  }));
}

async function devTo(service, args, options) {
  const candidate =
    args.hashtag || (/^[a-z0-9-]{1,30}$/i.test(args.query) ? args.query : "");
  const tag = candidate.toLowerCase();
  if (!tag) return [];
  const url = new URL("https://dev.to/api/articles");
  url.searchParams.set("tag", tag);
  url.searchParams.set("per_page", String(args.maximum));
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/vnd.forem.api-v1+json",
      max_chars: 512_000,
      cache_namespace: "social-devto",
      attempts: 2,
    },
    options,
  );
  return JSON.parse(response.text).map((item) => ({
    platform: "devto",
    url: item.url,
    author: item.user?.name || item.user?.username || "",
    title: cleanSocial(item.title, 500),
    content: cleanSocial(item.description),
    published_at: item.published_at ?? item.created_at ?? "",
    tags: (item.tag_list ?? []).slice(0, 10),
    metrics: {
      reactions: item.public_reactions_count ?? 0,
      comments: item.comments_count ?? 0,
    },
    provider: "devto-public-api",
  }));
}

async function discourse(service, args, options) {
  const url = new URL("/search.json", service.discourseUrl);
  url.searchParams.set("q", args.query);
  const response = await service.readText(
    {
      url: url.href,
      accept: "application/json",
      max_chars: 512_000,
      cache_namespace: "social-discourse",
      attempts: 2,
    },
    options,
  );
  const value = JSON.parse(response.text);
  const posts = new Map(
    (value.posts ?? []).map((post) => [post.topic_id, post]),
  );
  return (value.topics ?? []).slice(0, args.maximum).map((topic) => {
    const post = posts.get(topic.id);
    return {
      platform: "discourse",
      url: new URL(`/t/${topic.slug}/${topic.id}`, service.discourseUrl).href,
      author: post?.username ?? "",
      title: cleanSocial(topic.title, 500),
      content: cleanSocial(post?.blurb),
      published_at: post?.created_at ?? topic.bumped_at ?? "",
      metrics: {
        posts: topic.posts_count ?? 0,
        views: topic.views ?? 0,
        likes: topic.like_count ?? 0,
      },
      provider: "discourse-public-search",
    };
  });
}

function pipedResultUrl(value) {
  try {
    const url = new URL(value, "https://www.youtube.com");
    const host = url.hostname.toLowerCase();
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.port ||
      !(
        host === "youtu.be" ||
        host === "youtube.com" ||
        host.endsWith(".youtube.com")
      )
    )
      return "";
    url.hash = "";
    return url.href;
  } catch {
    return "";
  }
}

function pipedPublishedAt(item) {
  const uploaded = Number(item.uploaded);
  if (Number.isFinite(uploaded) && uploaded > 0) {
    const value = new Date(uploaded);
    if (!Number.isNaN(value.valueOf())) return value.toISOString();
  }
  return cleanSocial(item.uploadedDate, 100);
}

async function youtube(service, args, options) {
  let lastError;
  const pipedUrls = service.pipedUrls ?? [];
  for (const baseUrl of pipedUrls) {
    const url = new URL("/search", baseUrl);
    url.searchParams.set("q", args.query);
    url.searchParams.set("filter", "videos");
    const timeout =
      service.timeoutSignal?.(3_500) ?? AbortSignal.timeout(3_500);
    const signal = options?.signal
      ? AbortSignal.any([options.signal, timeout])
      : timeout;
    try {
      const response = await service.readText(
        {
          url: url.href,
          accept: "application/json",
          max_chars: 512_000,
          cache_namespace: `social-youtube-${url.hostname}`,
          attempts: 1,
        },
        { ...options, signal },
      );
      const value = JSON.parse(response.text);
      const items = Array.isArray(value.items)
        ? value.items
        : Array.isArray(value)
          ? value
          : [];
      return items
        .filter((item) => item.type === "stream" || item.videoId || item.url)
        .flatMap((item) => {
          const itemUrl = pipedResultUrl(
            item.url || (item.videoId ? `/watch?v=${item.videoId}` : ""),
          );
          if (!itemUrl) return [];
          return [
            {
              platform: "youtube",
              url: itemUrl,
              author: cleanSocial(item.uploaderName || item.author, 200),
              title: cleanSocial(item.title, 500),
              content: cleanSocial(item.shortDescription),
              published_at: pipedPublishedAt(item),
              metrics: {
                views: Number(item.views) || 0,
                duration_seconds: Number(item.duration) || 0,
              },
              provider: `piped-${url.hostname}`,
            },
          ];
        })
        .slice(0, args.maximum);
    } catch (error) {
      if (options?.signal?.aborted) throw error;
      lastError = error;
    }
  }
  throw Object.assign(
    new Error(
      pipedUrls.length
        ? "All configured public Piped instances failed"
        : "No public Piped instance is configured",
    ),
    {
      status: lastError?.status ?? 503,
      code: "alta_social_youtube_unavailable",
    },
  );
}

async function stocktwits(service, args, options) {
  if (!args.symbol) return [];
  const url = new URL(
    `/api/2/streams/symbol/${encodeURIComponent(args.symbol)}.json`,
    "https://api.stocktwits.com",
  );
  let response;
  try {
    response = await service.readText(
      {
        url: url.href,
        accept: "application/json",
        max_chars: 512_000,
        cache_namespace: "social-stocktwits",
        attempts: 1,
      },
      options,
    );
  } catch (error) {
    throw Object.assign(
      new Error(
        `Stocktwits public stream unavailable${error.status ? ` (HTTP ${error.status})` : ""}`,
      ),
      {
        status: error.status ?? 503,
        code: "alta_social_stocktwits_unavailable",
      },
    );
  }
  return (JSON.parse(response.text).messages ?? [])
    .slice(0, args.maximum)
    .flatMap((message) => {
      const username = message.user?.username;
      if (!username || !message.id) return [];
      return [
        {
          platform: "stocktwits",
          url: `https://stocktwits.com/${username}/message/${message.id}`,
          author: cleanSocial(message.user?.name || username, 200),
          handle: username,
          title: cleanSocial(message.body, 280),
          content: cleanSocial(message.body),
          published_at: message.created_at ?? "",
          symbol: args.symbol,
          sentiment: cleanSocial(message.entities?.sentiment?.basic, 40),
          metrics: {
            likes: Number(message.likes?.total) || 0,
            reshares: Number(message.reshare_message?.reshared_count) || 0,
          },
          provider: "stocktwits-public-stream",
        },
      ];
    });
}

const ADAPTERS = {
  bluesky,
  hackernews: hackerNews,
  lemmy,
  mastodon,
  reddit,
  stackexchange: stackExchange,
  peertube: peerTube,
  devto: devTo,
  discourse,
  youtube,
  stocktwits,
};

export function searchDirectSocial(service, platform, args, options) {
  return ADAPTERS[platform](service, args, options);
}
