"use client";

import { useEffect, useRef, useState } from "react";

import { ResultCard } from "@/components/ResultCard";
import { ApiError, analyze, fetchDomains } from "@/lib/api";
import type { AnalyzeResponse, DomainsResponse } from "@/lib/types";

export default function Home() {
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [domains, setDomains] = useState<DomainsResponse | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    setResult(null);

    if (imageUrl) URL.revokeObjectURL(imageUrl);
    setImageUrl(URL.createObjectURL(file));

    try {
      setResult(await analyze(file));
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
  }

  return (
    <main className="page">
      <header className="hero">
        <h1 className="hero__title">BioVision</h1>
        <p className="hero__subtitle">
          Ne bilmediğini söyleyen bir hasar analizi sistemi.
        </p>
        <p className="hero__body">
          Bir hasar fotoğrafı yükleyin. Sistem önce fotoğrafın hangi alana ait
          olduğunu belirler; o alan için eğitilmiş bir uzman modeli varsa ölçüm
          yapar, yoksa <strong>bunu açıkça söyler</strong>.
        </p>
      </header>

      {domains && <DomainList domains={domains} />}

      <section
        className="dropzone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
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
          }}
        />
        <button
          type="button"
          className="dropzone__button"
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
    </main>
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
