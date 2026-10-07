// src/components/SourceIcon.tsx
import { useState } from "react";
import type { Source } from "../App";
import { DATA_SOURCE_LABELS, getFaviconDomain, resolveDataSourceType } from "../lib/dataSourceType";
import { SourceGlyph } from "./SourceGlyph";

interface SourceIconProps {
  source: Source;
  className?: string;
}

export function SourceIcon({ source, className }: SourceIconProps) {
  const type = resolveDataSourceType(source);
  const label = DATA_SOURCE_LABELS[type];
  const showFavicon =
    type === "generic_web" && Boolean(source.has_external_link && source.url);

  const [faviconFailed, setFaviconFailed] = useState(false);

  const boxClass = ["src-favicon", `src-favicon--type-${type}`, className].filter(Boolean).join(" ");

  if (showFavicon && !faviconFailed) {
    const domain = getFaviconDomain(source);
    return (
      <span className={boxClass} title={label}>
        <img
          src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`}
          alt=""
          onError={() => setFaviconFailed(true)}
        />
      </span>
    );
  }

  return (
    <span className={boxClass} title={label}>
      <SourceGlyph type={type} className="src-glyph" />
    </span>
  );
}
