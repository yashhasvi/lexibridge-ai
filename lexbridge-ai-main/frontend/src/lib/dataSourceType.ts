/**
 * Normalized corpus / web source kinds for UI branding (icons + labels).
 * Backend can set `metadata.source_kind` to one of these; otherwise we infer from domain / URL.
 */

export type DataSourceType =
  | "wikipedia"
  | "stackoverflow"
  | "stackexchange"
  | "reddit"
  | "github"
  | "arxiv"
  | "medium"
  | "youtube"
  | "hackernews"
  | "twitter"
  | "government"
  | "education"
  | "news"
  | "reading_comprehension"
  | "internal_index"
  | "generic_web";

export const DATA_SOURCE_LABELS: Record<DataSourceType, string> = {
  wikipedia: "Wikipedia",
  stackoverflow: "Stack Overflow",
  stackexchange: "Stack Exchange",
  reddit: "Reddit",
  github: "GitHub",
  arxiv: "arXiv",
  medium: "Medium",
  youtube: "YouTube",
  hackernews: "Hacker News",
  twitter: "X / Twitter",
  government: "Government",
  education: "Academic (.edu)",
  news: "News",
  reading_comprehension: "Reading comprehension dataset",
  internal_index: "Canonical index",
  generic_web: "Web",
};

const KIND_ALIASES: Record<string, DataSourceType> = {
  wikipedia: "wikipedia",
  wiki: "wikipedia",
  stackoverflow: "stackoverflow",
  so: "stackoverflow",
  stackexchange: "stackexchange",
  se: "stackexchange",
  reddit: "reddit",
  github: "github",
  arxiv: "arxiv",
  medium: "medium",
  youtube: "youtube",
  hackernews: "hackernews",
  hn: "hackernews",
  twitter: "twitter",
  x: "twitter",
  government: "government",
  gov: "government",
  education: "education",
  edu: "education",
  academic: "education",
  news: "news",
  reading_comprehension: "reading_comprehension",
  squad: "reading_comprehension",
  natural_questions: "reading_comprehension",
  hotpot: "reading_comprehension",
  nq: "reading_comprehension",
  internal: "internal_index",
  internal_index: "internal_index",
  canonical: "internal_index",
  canonicalqa: "internal_index",
  corpus: "internal_index",
  web: "generic_web",
  generic: "generic_web",
};

function normalizeHost(domain?: string, url?: string): string {
  const d = domain?.trim().toLowerCase().replace(/^www\./, "");
  if (d) return d;
  if (!url) return "";
  try {
    return new URL(url).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return "";
  }
}

/** Host string for favicon services (falls back so the request still returns an icon). */
export function getFaviconDomain(source: SourceLike): string {
  return normalizeHost(source.domain, source.url) || "example.com";
}

function hostEndsWith(host: string, root: string): boolean {
  return host === root || host.endsWith(`.${root}`);
}

function isVerifiedInternalLike(s: SourceLike): boolean {
  if (s.has_external_link && s.url) return false;
  const meta = s.metadata;
  if (meta?.verified_internal === true) return true;
  return Boolean(!s.url && s.has_external_link === false);
}

export interface SourceLike {
  domain?: string;
  url?: string;
  has_external_link?: boolean;
  metadata?: Record<string, unknown>;
}

export function resolveDataSourceType(s: SourceLike): DataSourceType {
  const rawKind = s.metadata?.source_kind;
  if (typeof rawKind === "string") {
    const mapped = KIND_ALIASES[rawKind.trim().toLowerCase().replace(/\s+/g, "_")];
    if (mapped) return mapped;
  }

  if (isVerifiedInternalLike(s)) {
    return "internal_index";
  }

  const host = normalizeHost(s.domain, s.url);
  if (!host) {
    return s.has_external_link && s.url ? "generic_web" : "internal_index";
  }

  if (hostEndsWith(host, "wikipedia.org")) return "wikipedia";
  if (host === "stackoverflow.com" || hostEndsWith(host, ".stackoverflow.com")) return "stackoverflow";
  if (hostEndsWith(host, "stackexchange.com")) return "stackexchange";
  if (host === "reddit.com" || hostEndsWith(host, ".reddit.com")) return "reddit";
  if (host === "github.com" || hostEndsWith(host, ".github.com")) return "github";
  if (host === "arxiv.org" || hostEndsWith(host, ".arxiv.org")) return "arxiv";
  if (host === "medium.com" || hostEndsWith(host, ".medium.com")) return "medium";
  if (host === "youtube.com" || host === "youtu.be" || hostEndsWith(host, ".youtube.com")) return "youtube";
  if (host === "news.ycombinator.com") return "hackernews";
  if (host === "twitter.com" || host === "x.com" || hostEndsWith(host, ".twitter.com")) return "twitter";

  if (host.endsWith(".gov") || host.endsWith(".gov.uk") || host.endsWith(".go.jp")) return "government";
  if (host.endsWith(".edu") || host.endsWith(".ac.uk")) return "education";

  if (
    hostEndsWith(host, "nytimes.com") ||
    hostEndsWith(host, "theguardian.com") ||
    hostEndsWith(host, "reuters.com") ||
    hostEndsWith(host, "bbc.co.uk") ||
    hostEndsWith(host, "bbc.com") ||
    hostEndsWith(host, "washingtonpost.com") ||
    hostEndsWith(host, "apnews.com")
  ) {
    return "news";
  }

  return "generic_web";
}
