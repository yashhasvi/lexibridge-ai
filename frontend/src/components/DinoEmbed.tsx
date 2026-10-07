import React from "react";

export const DinoEmbed: React.FC = () => {
  return (
    <div className="sketchfab-embed-wrapper">
      <iframe
        title="Pearannosaurus rex (P-Rex)"
        allowFullScreen
        allow="autoplay; fullscreen; xr-spatial-tracking"
        src="https://sketchfab.com/models/1e34904802744d579449f52056c09c72/embed?dnt=1"
        style={{ width: '100%', height: '480px', border: 'none' }}
      ></iframe>
      <p style={{ fontSize: 13, fontWeight: "normal", margin: 5, color: "#4A4A4A" }}>
        <a
          href="https://sketchfab.com/3d-models/pearannosaurus-rex-p-rex-1e34904802744d579449f52056c09c72?utm_medium=embed&utm_campaign=share-popup&utm_content=1e34904802744d579449f52056c09c72"
          target="_blank"
          rel="nofollow"
          style={{ fontWeight: "bold", color: "#1CAAD9" }}
        >
          Pearannosaurus rex (P-Rex)
        </a>{" "}
        by{" "}
        <a
          href="https://sketchfab.com/mariotormo?utm_medium=embed&utm_campaign=share-popup&utm_content=1e34904802744d579449f52056c09c72"
          target="_blank"
          rel="nofollow"
          style={{ fontWeight: "bold", color: "#1CAAD9" }}
        >
          mariotormo
        </a>{" "}
        on{" "}
        <a
          href="https://sketchfab.com?utm_medium=embed&utm_campaign=share-popup&utm_content=1e34904802744d579449f52056c09c72"
          target="_blank"
          rel="nofollow"
          style={{ fontWeight: "bold", color: "#1CAAD9" }}
        >
          Sketchfab
        </a>
      </p>
    </div>
  );
};