export const PLATFORM_DOMAINS = {
  bluesky: ["bsky.app"],
  hackernews: ["news.ycombinator.com"],
  lemmy: ["lemmy.world", "lemmy.ml"],
  mastodon: ["mastodon.social"],
  reddit: ["reddit.com"],
  stackexchange: [
    "stackoverflow.com",
    "stackexchange.com",
    "superuser.com",
    "serverfault.com",
    "askubuntu.com",
  ],
  peertube: ["peertube.tv", "joinpeertube.org"],
  devto: ["dev.to"],
  discourse: ["meta.discourse.org"],
  nostr: ["njump.me", "nostr.band", "primal.net"],
  youtube: ["youtube.com", "youtu.be"],
  x: ["x.com", "twitter.com"],
  tiktok: ["tiktok.com"],
  instagram: ["instagram.com"],
  threads: ["threads.net"],
  linkedin: ["linkedin.com"],
  facebook: ["facebook.com"],
  weibo: ["weibo.com"],
  zhihu: ["zhihu.com"],
  bilibili: ["bilibili.com"],
  douyin: ["douyin.com"],
  xiaohongshu: ["xiaohongshu.com"],
  telegram: ["t.me", "telegram.me"],
  pinterest: ["pinterest.com"],
  tumblr: ["tumblr.com"],
  medium: ["medium.com"],
  substack: ["substack.com"],
  vk: ["vk.com"],
  quora: ["quora.com"],
  twitch: ["twitch.tv"],
  snapchat: ["snapchat.com"],
  kuaishou: ["kuaishou.com"],
  toutiao: ["toutiao.com"],
  douban: ["douban.com"],
  v2ex: ["v2ex.com"],
  segmentfault: ["segmentfault.com"],
  juejin: ["juejin.cn"],
  stocktwits: ["stocktwits.com"],
  tradingview: ["tradingview.com"],
  bitcointalk: ["bitcointalk.org"],
  elitetrader: ["elitetrader.com"],
  forexfactory: ["forexfactory.com"],
  bogleheads: ["bogleheads.org"],
  tradingqna: ["tradingqna.com"],
  mql5: ["mql5.com"],
  quantnet: ["quantnet.com"],
  wallstreetoasis: ["wallstreetoasis.com"],
  investorshub: ["investorshub.advfn.com"],
};

export function platformForUrl(value) {
  try {
    const host = new URL(value).hostname.toLowerCase().replace(/^www\./, "");
    return (
      Object.entries(PLATFORM_DOMAINS).find(([, domains]) =>
        domains.some(
          (domain) => host === domain || host.endsWith(`.${domain}`),
        ),
      )?.[0] ?? "web"
    );
  } catch {
    return "web";
  }
}

export function configuredSocialDomains(service, platforms) {
  const domains = platforms.flatMap((platform) => PLATFORM_DOMAINS[platform]);
  for (const [platform, configuredUrl] of [
    ["lemmy", service.lemmyUrl],
    ["mastodon", service.mastodonUrl],
    ["peertube", service.peertubeUrl],
    ["discourse", service.discourseUrl],
  ]) {
    if (!platforms.includes(platform)) continue;
    try {
      domains.push(new URL(configuredUrl).hostname);
    } catch {}
  }
  return [...new Set(domains)];
}
