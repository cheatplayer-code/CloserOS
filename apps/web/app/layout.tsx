import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Providers } from "../components/providers";

import "./styles.css";

export const metadata: Metadata = {
  title: "CloserOS AI",
  description: "Authentication and workspace access for CloserOS AI",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
