import { useEffect } from "react";

/** Shows the configured logo as the browser-tab icon, or the default mark. */
export function useFavicon(logoUrl?: string) {
  useEffect(() => {
    const link = document.getElementById("favicon");
    if (!(link instanceof HTMLLinkElement) || !logoUrl) return;
    const defaultHref = link.href;
    const defaultType = link.type;
    link.href = logoUrl;
    link.removeAttribute("type");
    return () => {
      link.href = defaultHref;
      link.type = defaultType;
    };
  }, [logoUrl]);
}
