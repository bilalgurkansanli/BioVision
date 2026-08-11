"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  deleteAllAnalyses,
  deleteAnalysis,
  fetchHistory,
} from "@/lib/api";
import { authConfigured, currentAccessToken, signInWithGoogle, signOut } from "@/lib/supabase";
import type { HistoryItem } from "@/lib/types";

export default function HistoryPage() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [retentionDays, setRetentionDays] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    currentAccessToken()
      .then(setToken)
      .finally(() => setReady(true));
  }, []);

  const load = useCallback(async (accessToken: string) => {
    try {
      const history = await fetchHistory(accessToken);
      setItems(history.items);
      setRetentionDays(history.retention_days);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Geçmiş yüklenemedi.");
    }
  }, []);

  useEffect(() => {
    if (token) void load(token);
  }, [token, load]);

  if (!ready) return <main className="page">Yükleniyor…</main>;

  if (!token) {
    return (
      <main className="page">
        <h1 className="hero__title">Geçmişiniz</h1>
        {authConfigured ? (
          <>
            <p>
              Analiz geçmişinizi görmek için giriş yapın. Giriş yapmadan da
              analiz yapabilirsiniz — sadece kayıt tutulmaz.
            </p>
            <button
              type="button"
              className="dropzone__button"
              onClick={() => void signInWithGoogle()}
            >
              Google ile giriş yap
            </button>
          </>
        ) : (
          <p>
            Bu ortamda giriş yapılandırılmamış. Analiz yapmaya{" "}
            <Link href="/">ana sayfadan</Link> devam edebilirsiniz.
          </p>
        )}
      </main>
    );
  }

  return (
    <main className="page">
      <header>
        <h1 className="hero__title">Geçmişiniz</h1>
        <p className="hero__body">
          {retentionDays !== null && (
            <>
              Analizler ve saklanan görseller <strong>{retentionDays} gün</strong>{" "}
              sonra otomatik olarak silinir. Dilediğiniz zaman daha erken de
              silebilirsiniz.
            </>
          )}
        </p>
      </header>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <p>Henüz kayıtlı analiziniz yok.</p>
      ) : (
        <ul className="domains__list" style={{ gridTemplateColumns: "1fr" }}>
          {items.map((item) => (
            <HistoryRow
              key={item.id}
              item={item}
              onDelete={async () => {
                await deleteAnalysis(item.id, token);
                setItems((current) => current.filter((row) => row.id !== item.id));
              }}
            />
          ))}
        </ul>
      )}

      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
        {items.length > 0 && (
          <button
            type="button"
            className="history__delete"
            onClick={async () => {
              // Irreversible and complete, so it is confirmed rather than
              // instant -- the one action here a user cannot undo.
              if (!confirm("Tüm analizleriniz ve görselleriniz kalıcı olarak silinecek. Emin misiniz?")) {
                return;
              }
              await deleteAllAnalyses(token);
              setItems([]);
            }}
          >
            Tüm verilerimi sil
          </button>
        )}
        <button
          type="button"
          className="history__delete"
          style={{ color: "inherit" }}
          onClick={async () => {
            await signOut();
            setToken(null);
          }}
        >
          Çıkış yap
        </button>
      </div>
    </main>
  );
}

function HistoryRow({
  item,
  onDelete,
}: {
  item: HistoryItem;
  onDelete: () => Promise<void>;
}) {
  // Same three-way distinction as the result card: a stored analysis with no
  // specialist behind it is not a lesser measurement, it is a different kind of
  // answer, and the list says so at a glance.
  const kind =
    item.specialist_model !== null
      ? "measured"
      : item.warning === "low_domain_confidence"
        ? "unplaced"
        : "described";

  const summary =
    kind === "measured"
      ? `${item.findings.length} bulgu · ${item.specialist_model}`
      : kind === "unplaced"
        ? "alan belirlenemedi"
        : "uzman model yok — ölçüm yapılmadı";

  return (
    <li className={`history__item history__item--${kind}`}>
      <span>
        <strong>{item.domain}</strong>
        <span className="history__meta"> · {summary}</span>
      </span>
      <span className="history__meta">
        {new Date(item.created_at).toLocaleString("tr-TR")}
      </span>
      <button type="button" className="history__delete" onClick={() => void onDelete()}>
        Sil
      </button>
    </li>
  );
}
