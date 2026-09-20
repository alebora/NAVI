import "./styles.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "NAVI Meetings",
  description: "Audio meeting summaries recorded by NAVI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
