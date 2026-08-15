import type { Metadata } from "next";

import { DocLinks } from "@/components/DocLinks";

export const metadata: Metadata = {
  title: "Lisans ve kaynaklar",
  description:
    "AGPL-3.0 lisansı, kullanılan modeller ve veri setleri, ve her birinin kaynağı ile lisansı.",
  alternates: { canonical: "/lisans" },
};

export default function LicencePage() {
  return (
    <main className="doc">
      <header className="doc__header">
        <p className="doc__kicker">Belge</p>
        <h1 className="doc__title">Lisans ve kaynaklar</h1>
        <p className="doc__lead">
          Bu sistemin dayandığı her bileşen ve nereden geldiği. Atıf gerektiren
          her şey burada.
        </p>
      </header>

      <section className="doc__section">
        <h2>Yazılım</h2>
        <p>
          BioVision, <strong>GNU Affero General Public License v3</strong> ile
          lisanslıdır. Ultralytics YOLO&apos;ya bağlı olduğu için AGPL zorunludur ve
          bir tercih değildir.
        </p>
        <p>
          AGPL&apos;in pratik sonucu: bu yazılımın değiştirilmiş bir sürümünü ağ
          üzerinden servis olarak sunarsanız, kullanıcılarına kaynak kodunu
          sunmakla yükümlüsünüz.
        </p>
        <p>
          <a
            href="https://github.com/bilalgurkansanli/BioVision"
            rel="noopener noreferrer"
            target="_blank"
          >
            Kaynak kodu GitHub&apos;da
          </a>
          .
        </p>
      </section>

      <section className="doc__section">
        <h2>Modeller</h2>
        <dl className="facts">
          <dt>Alan sınıflandırma</dt>
          <dd>
            CLIP ViT-B/32 (LAION-2B). Fotoğrafın hasar fotoğrafı olup olmadığına
            ve hangi alana ait olduğuna karar verir.
          </dd>

          <dt>Yüz tespiti</dt>
          <dd>
            YuNet (OpenCV Zoo, MIT lisansı). Bulanıklaştırma için yüzleri bulur.
          </dd>

          <dt>Araç hasarı</dt>
          <dd>
            Ultralytics YOLO segmentasyon, VehiDE üzerinde eğitilmiş. AGPL-3.0.
          </dd>

          <dt>Serbest metin açıklama</dt>
          <dd>Claude Haiku (Anthropic), yalnızca uzman modeli olmayan alanlarda.</dd>
        </dl>
      </section>

      <section className="doc__section">
        <h2>Veri setleri</h2>
        <p>
          Araç hasarı modeli <strong>VehiDE</strong> veri seti üzerinde eğitilir:
          13.945 fotoğraf, 36.081 işaretlenmiş hasar örneği, bir sigorta
          şirketinin hasar değerlendirme standartlarına göre etiketlenmiş.
        </p>
        <blockquote className="citation">
          N. T. Huynh, N. N. D. Tran, A. T. Huynh, V.-D. Hoang ve H. D. Nguyen,
          &ldquo;VehiDE Dataset: New dataset for Automatic vehicle damage detection
          in Car insurance,&rdquo; <em>2023 15th International Conference on
          Knowledge and Systems Engineering (KSE)</em>, IEEE, 2023.
          doi:10.1109/KSE59128.2023.10299490
        </blockquote>
        <p className="citation__note">
          Veri seti bu depoda yeniden dağıtılmaz. Eğitim not defteri, kendi
          kopyanızı kullanır ve bölme ile rastgelelik tohumu sabitlenmiştir — yani
          yayınlanan sayılar yeniden üretilebilir.
        </p>
      </section>

      <section className="doc__section">
        <h2>Neyin ölçüldüğü, neyin ölçülmediği</h2>
        <p>
          Bu projenin asıl iddiası burada: her sayı bir ölçüme dayanır ve
          ölçülmemiş olan boş bırakılır, tahminle doldurulmaz.
        </p>
        <p>
          <a
            href="https://github.com/bilalgurkansanli/BioVision#what-is-proven-and-what-is-not"
            rel="noopener noreferrer"
            target="_blank"
          >
            Kanıtlananlar ve kanıtlanmayanlar tablosu
          </a>{" "}
          README&apos;nin başındadır — hangi iddianın arkasında hangi testin
          olduğu, ve hangilerinin henüz kanıtı bulunmadığı yazılıdır.
        </p>
      </section>

      <DocLinks current="/lisans" />
    </main>
  );
}
