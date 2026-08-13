import type { Metadata } from "next";
import { Suspense } from "react";

import { CallbackHandler } from "./CallbackHandler";

export const metadata: Metadata = {
  title: "Giriş tamamlanıyor",
  robots: { index: false, follow: false },
};

export default function AuthCallbackPage() {
  return (
    <main className="page">
      <Suspense fallback={<p>Giriş tamamlanıyor…</p>}>
        <CallbackHandler />
      </Suspense>
    </main>
  );
}
