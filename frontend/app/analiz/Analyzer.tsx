"use client";

/**
 * The analyser.
 *
 * This used to live at `/`, which meant the page that had to rank for "hasar
 * analizi" was a client component whose entire body was empty until a user
 * uploaded something. Moving it here lets `/` be server-rendered prose and lets
 * this page be what it actually is: a tool.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ResultCard } from "@/components/ResultCard";
import { ApiError, analyze, fetchDomains } from "@/lib/api";
import { currentAccessToken } from "@/lib/supabase";
import type { AnalyzeResponse, DomainsResponse } from "@/lib/types";

export function Analyzer() {
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [domains, setDomains] = useState<DomainsResponse | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // dragenter/dragleave fire for every child element the pointer crosses, so a
  // boolean flag flickers as the cursor moves over the button inside the zone.
  // Counting enters and leaves is the standard fix.
  const dragDepth = useRef(0);

  useEffect(() => {
    fetchDomains().then(setDomains).catch(() => setDomains(null));
  }, []);

  // Object URLs leak until revoked, and a user analysing a dozen photos would
  // pin every one of them in memory.
  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl);
    };
  }, [imageUrl]);

  const handleFile = useCallback(async (file: File) => {
    setBusy(true);
    setError(null);
    setResult(null);

    setImageUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return URL.createObjectURL(file);
    });

    try {
      // The token has to be attached here, not just on the history page.
      // Without it the API treats a signed-in user as anonymous: the analysis
      // is never stored, so their history stays permanently empty, and the
      // request is charged against the anonymous quota. Found by signing in and
      // looking at the history page, which is the only place the symptom shows.
      const accessToken = await currentAccessToken();
      setResult(await analyze(file, { accessToken: accessToken ?? undefined }));
    } catch (caught) {
      // Every documented failure already has a human sentence attached; this is
      // only the safety net for something genuinely unexpected.
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Beklenmeyen bir hata oluştu.",
      );
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <>
      {domains && <DomainList domains={domains} />}

      <section
        className={[
          "dropzone",
          dragging ? "dropzone--dragging" : "",
          busy ? "dropzone--busy" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        onDragEnter={(event) => {
          event.preventDefault();
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => {
          dragDepth.current -= 1;
          if (dragDepth.current <= 0) {
            dragDepth.current = 0;
            setDragging(false);
          }
        }}
        onDrop={(event) => {
          event.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) void handleFile(file);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,.heic"
          className="dropzone__input"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleFile(file);
            // Without this, choosing the same file twice in a row fires no
            // change event and the second attempt silently does nothing.
            event.target.value = "";
          }}
        />
        <button
          type="button"
          className="btn btn--primary"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? "Analiz ediliyor…" : "Fotoğraf seç"}
        </button>
        <p className="dropzone__hint">
          veya sürükleyip bırakın · JPEG, PNG, WebP, HEIC · en fazla 10 MB
        </p>
        <p className="dropzone__privacy">
          Yüzler bulanıklaştırılır ve konum verisi silinir. Yüklediğiniz orijinal
          dosya hiçbir yerde saklanmaz.
        </p>
      </section>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      {result && imageUrl && <ResultCard result={result} imageUrl={imageUrl} />}
    </>
  );
}

/**
 * Which domains have a model behind them, stated before the user uploads
 * anything. Setting the expectation up front is more honest than letting them
 * discover it from a result.
 */
function DomainList({ domains }: { domains: DomainsResponse }) {
  return (
    <section className="domains">
      <h2 className="domains__title">
        Desteklenen alanlar
        <span className="domains__count">
          {domains.with_specialist} / {domains.count} tanesinde uzman model var
        </span>
      </h2>
      <ul className="domains__list">
        {domains.domains.map((domain) => (
          <li
            key={domain.key}
            className={`domain ${domain.has_specialist ? "domain--specialist" : ""}`}
          >
            <span className="domain__label">{domain.label}</span>
            <span className="domain__status">
              {domain.has_specialist ? "uzman model var" : "uzman model yok"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
