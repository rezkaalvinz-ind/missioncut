import type { Metadata } from "next";
import type { Viewport } from "next";
import "./globals.css";
import "./responsive.css";

export const metadata: Metadata = {
  title: "MissionCut — Containment, with context",
  description: "Model incident containment options against reachable assets, critical services, and route-level impact.",
  applicationName: "MissionCut",
  keywords: ["incident response", "containment", "network topology", "cybersecurity simulator"],
  robots: { index: true, follow: true },
  openGraph: {
    type: "website",
    title: "MissionCut — Containment, with context",
    description: "Offline containment decision support for synthetic and uploaded asset graphs.",
    siteName: "MissionCut",
  },
};

export const viewport: Viewport = { themeColor: "#03030a", colorScheme: "dark" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a className="skip-link" href="#main-content">Skip to workspace</a>{children}</body></html>;
}
