"use client";

import { damageLabel, severityLabel } from "@/lib/labels";
import type { ClaimSummary } from "@/lib/types";

/**
 * What a claim's photographs establish together.
 *
 * The measurement behind it: over 250 real multi-photograph claims from VehiDE,
 * the union across a claim surfaces 2.04 damage types against 1.57 from any
 * single photograph, and the gain grows with the count (README 7.12).
 *
 * Three things this copy is careful about, each a place the summary could
 * mislead a reader who is not holding the README:
 *
 * 1. **A wider view is not more damage.** Two types instead of one is not twice
 *    the loss, and the wording says "toplu görünüm" rather than a total.
 * 2. **The band is the worst photograph's, not an average.** Said out loud,
 *    because a reader who assumes an average will read a severe claim as milder
 *    the more photographs were sent.
 * 3. **`partial` is not a contradiction.** One frame may honestly show an
 *    undamaged panel of a damaged car. Calling it a disagreement would invent a
 *    problem the measurement does not support.
 */
export function ClaimSummaryCard({ summary }: { summary: ClaimSummary }) {
  const { photo_count, photos_with_findings, agreement, damage_types } = summary;

  return (
    <section className="photoset">
      <h2 className="photoset__title">
        Bu ihbarın {photo_count} fotoğrafı birlikte ne söylüyor
      </h2>

      {damage_types.length > 0 ? (
        <p className="photoset__types">
          <strong>{damage_types.map(damageLabel).join(", ")}</strong>
          <span className="photoset__note">
            Fotoğrafların toplu görünümü. Aynı hasar birden fazla karede
            görünüyorsa bir kez sayılır — bu liste hasarın <em>tamamını</em>{" "}
            görmek demek, daha <em>fazla</em> hasar demek değil.
          </span>
        </p>
      ) : (
        <p className="photoset__types">
          <strong>Hiçbir fotoğrafta bulgu yok</strong>
          <span className="photoset__note">
            Bu, aracın hasarsız olduğu anlamına gelmez; yalnızca gönderilen
            karelerde bir şey bulunamadığı anlamına gelir.
          </span>
        </p>
      )}

      {summary.overall_severity && (
        <p className="photoset__band">
          Genel değerlendirme:{" "}
          <strong>{severityLabel(summary.overall_severity)}</strong>
          <span className="photoset__note">
            Fotoğrafların <em>en ağırı</em>, ortalaması değil. Bir ihbar en kötü
            görünümü kadar ağırdır; ortalama alsaydık, aracın tamamını
            fotoğraflayan bir kullanıcının hasarı daha hafif görünürdü.
          </span>
        </p>
      )}

      <p className="photoset__agreement">
        {agreement === "all" && (
          <>
            <strong>{photo_count} fotoğrafın hepsinde</strong> bulgu var.
            <span className="photoset__note">
              Fotoğraflar birbirini destekliyor. Bu, modelin kendi puanından
              gelmeyen bir güven işareti — ölçtüğümüz 250 ihbarın 224&apos;ü
              böyleydi.
            </span>
          </>
        )}
        {agreement === "partial" && (
          <>
            <strong>
              {photos_with_findings}/{photo_count} fotoğrafta
            </strong>{" "}
            bulgu var.
            <span className="photoset__note">
              Bu bir çelişki olmayabilir: bir kare, hasarlı bir aracın sağlam
              panelini gösteriyor olabilir. Hangisi olduğunu söylemek aracın
              hangi yönden çekildiğini bilmeyi gerektirir, o bilgi bizde yok.
              Ölçtüğümüz 250 ihbarın 23&apos;ünde bu durum vardı.
            </span>
          </>
        )}
        {agreement === "none" && (
          <span className="photoset__note">
            Gönderilen karelerin hiçbirinde bulgu çıkmadı. Aracın tamamının
            göründüğü, yakın çekim bir fotoğraf eklemek sonucu değiştirebilir.
          </span>
        )}
      </p>
    </section>
  );
}
