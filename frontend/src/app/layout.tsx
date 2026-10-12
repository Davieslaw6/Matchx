import type { Metadata, Viewport } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "MATCH X — Football Analysis", description: "Private football analysis assistant with transparent statistical estimates." };
export const viewport: Viewport = { themeColor: "#10131b", width: "device-width", initialScale: 1 };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" data-theme="dark"><body><div className="responsible-notice" role="note">Statistical estimates only — not advice or guarantees. Follow local law and bookmaker terms.</div>{children}</body></html>;
}
