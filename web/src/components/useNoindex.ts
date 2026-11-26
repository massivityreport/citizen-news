import { useEffect } from "react";

/** Pose <meta name="robots" content="noindex"> tant que la page est affichée. */
export function useNoindex() {
  useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex";
    document.head.appendChild(meta);
    return () => {
      meta.parentNode?.removeChild(meta);
    };
  }, []);
}
