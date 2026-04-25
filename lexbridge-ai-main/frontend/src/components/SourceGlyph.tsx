// src/components/SourceGlyph.tsx
import type { ReactNode } from "react";
import type { DataSourceType } from "../lib/dataSourceType";

const common = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none" as const,
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function Glyph({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <svg {...common} className={className} aria-hidden>
      {children}
    </svg>
  );
}

export function SourceGlyph({ type, className }: { type: DataSourceType; className?: string }) {
  switch (type) {
    case "wikipedia":
      return (
        <Glyph className={className}>
          <circle cx="12" cy="12" r="9" />
          <path d="M3.6 12h16.8M12 3a15.3 15.3 0 0 1 4 9 15.3 15.3 0 0 1-4 9 15.3 15.3 0 0 1-4-9 15.3 15.3 0 0 1 4-9z" />
        </Glyph>
      );
    case "stackoverflow":
      return (
        <Glyph className={className}>
          <path d="M4 18h16M6 14L12 6l6 8M9 14h6M7 10h10" />
        </Glyph>
      );
    case "stackexchange":
      return (
        <Glyph className={className}>
          <rect x="4" y="5" width="16" height="5" rx="1" />
          <rect x="4" y="12" width="16" height="5" rx="1" />
          <path d="M8 8h8M8 15h5" />
        </Glyph>
      );
    case "reddit":
      return (
        <Glyph className={className}>
          <circle cx="12" cy="13" r="7" />
          <circle cx="9" cy="11" r="1.25" fill="currentColor" stroke="none" />
          <circle cx="15" cy="11" r="1.25" fill="currentColor" stroke="none" />
          <path d="M8 15s1.5 2 4 2 4-2 4-2" />
          <path d="M12 6v2M10 4l2 2 2-2" />
        </Glyph>
      );
    case "github":
      return (
        <Glyph className={className}>
          <path d="M8 9L5 12l3 3M16 9l3 3-3 3M11 7l2 9" />
        </Glyph>
      );
    case "arxiv":
      return (
        <Glyph className={className}>
          <path d="M7 4h10l-5 16-2-6-2 6-5-16z" />
          <path d="M9 10h6" />
        </Glyph>
      );
    case "medium":
      return (
        <Glyph className={className}>
          <circle cx="7.5" cy="12" r="3.5" />
          <circle cx="14" cy="12" r="2.75" />
        </Glyph>
      );
    case "youtube":
      return (
        <Glyph className={className}>
          <rect x="3" y="7" width="18" height="10" rx="2" fill="none" />
          <path d="M10 10v4l3.5-2L10 10z" fill="currentColor" stroke="none" />
        </Glyph>
      );
    case "hackernews":
      return (
        <Glyph className={className}>
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <path d="M8 16V8l4 5 4-5v8" />
        </Glyph>
      );
    case "twitter":
      return (
        <Glyph className={className}>
          <path d="M4 4l16 16M20 4L4 20" />
        </Glyph>
      );
    case "government":
      return (
        <Glyph className={className}>
          <path d="M3 21h18M5 21V10l7-4 7 4v11M9 21v-6h6v6" />
        </Glyph>
      );
    case "education":
      return (
        <Glyph className={className}>
          <path d="M4 11l8-4 8 4-8 4-8-4z" />
          <path d="M4 11v6l8 4M20 11v6" />
          <path d="M9 17v-4l3-1.5" />
        </Glyph>
      );
    case "news":
      return (
        <Glyph className={className}>
          <path d="M4 6h12a2 2 0 0 1 2 2v10H4V6z" />
          <path d="M8 10h6M8 14h4" />
        </Glyph>
      );
    case "reading_comprehension":
      return (
        <Glyph className={className}>
          <path d="M6 4h4v16H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4V4z" />
          <path d="M9 8h1M9 12h1M17 8h1M17 12h1" />
        </Glyph>
      );
    case "internal_index":
      return (
        <Glyph className={className}>
          <ellipse cx="12" cy="6" rx="7" ry="3" />
          <path d="M5 6v6c0 1.66 3.13 3 7 3s7-1.34 7-3V6" />
          <path d="M5 12v6c0 1.66 3.13 3 7 3s7-1.34 7-3v-6" />
        </Glyph>
      );
    case "generic_web":
    default:
      return (
        <Glyph className={className}>
          <circle cx="12" cy="12" r="9" />
          <path d="M3.6 12h16.8M12 3a15.3 15.3 0 0 1 4 9 15.3 15.3 0 0 1-4 9 15.3 15.3 0 0 1-4-9 15.3 15.3 0 0 1 4-9z" />
        </Glyph>
      );
  }
}
