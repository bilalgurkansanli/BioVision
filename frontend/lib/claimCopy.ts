/**
 * The claim-outcome copy, in certainty order.
 *
 * Ordered premium -> payout -> write-off, which is the reverse of what a
 * claimant asks. That is deliberate: the premium effect is arithmetic over a
 * published regulation and needs one input, the payout ceiling is a rule with an
 * unknowable amount underneath it, and the write-off line is exact while the side
 * is unknown. Leading with the most certain thing means every number the reader
 * meets is more solid than the one after it.
 *
 * **These strings were adversarially reviewed before they were written down.**
 * Three independent readers -- an insurance lawyer hunting implied promises, a
 * compliance reviewer checking every article, and a driver who had just crashed
 * their car -- found 11 fatal problems across four drafts, and each block was
 * rewritten against them. `backend/tests/unit/test_no_binding_language.py`
 * scans this file on every run and fails the build if a sentence ever promises
 * a payout, asserts a write-off, or repeats the 70% myth.
 *
 * Numbers in the prose are worked examples. The live figures come from
 * /v1/claims and are rendered separately, so a reader can tell an illustration
 * from their own case.
 */

export interface ClaimCitation {
  text_tr: string;
  source: string;
}

export interface ClaimBlock {
  /** Ordering is the argument; see the module comment. */
  order: number;
  heading_tr: string;
  body_tr: string;
  /** What this block deliberately does not tell the reader. */
  caveat_tr: string;
  citations: ClaimCitation[];
}

export const PREMIUM_BLOCK: ClaimBlock = {
  order: 1,
  heading_tr: "Bir ödeme, trafik basamağınızı nereye taşır",
  body_tr: "**Basamak, ödeme yapıldığında iner — kaza olduğunda değil.** Bir kaza için hiç tazminat ödenmezse basamak yerinde kalır. Ödeme yapılırsa: trafik sigortanızdan yapılan her maddi hasar ödemesi bir basamak, her bedeni hasar ödemesi iki basamak indirir. Buradaki merdiven trafik sigortasının merdivenidir. Kaskonuzdan yapılan ödemeler bu tabloyu değil, kendi kasko poliçenizde basılı hasarsızlık klozunu ilgilendirir; o kloz aşağıda anlatılıyor. Sayılan şey ödemedir; tek bir kazadan iki ayrı ödeme çıkarsa basamak iki kez iner. Hasarsız geçen her sigorta süresi bir basamak yukarı taşır — 8. basamak hariç, onun kuralı ayrı ve aşağıda anlatılıyor. Sisteme giriş 4. basamaktan olur.\n\nBasamağın karşılığı Ek-2'deki katsayıdır; bu katsayı, yıllık baz prime uygulanabilecek azami oranı gösterir. Baz prim, basamak katsayısı uygulanmadan önceki yıllık primdir; poliçede ödediğiniz rakam, baz primin bu katsayıyla çarpılmış hâlidir. Baz priminizi burada bilmiyoruz — aşağıdaki bütün yüzdeler, geçen yıl ödediğiniz primin değil, o baz primin üzerinedir. **8 = 0,50 · 7 = 0,60 · 6 = 0,80 · 5 = 0,95 · 4 = 1,10 · 3 = 1,45 · 2 = 1,90 · 1 = 2,35 · 0 = 3,00.** Bu tablo 15/4/2023'ten beri yürürlükte.\n\n**Örnek: 8. basamaktasınız ve bir maddi hasar ödemesi yapıldı.** Basamak 8'den 7'ye iner, katsayı 0,50 yerine 0,60 olur. İki katsayı arasındaki fark, bir yıllık baz primin %10'udur (0,60 − 0,50). Bu bir fiyat değil, iki tavan arasındaki farktır: Ek-2 azami primi bağlar, şirketin uygulayacağı oranı değil. Priminizin gerçekte ne kadar değiştiğini ancak yenileme teklifinde görürsünüz.\n\nBu örnek, tablodaki en küçük basamak farkıdır. Aşağı inildikçe fark büyür: 5'ten 4'e 0,15, 4'ten 3'e 0,35, 3'ten 2'ye 0,45. Kendi farkınız için tablodaki iki katsayıyı çıkarın; sonuç, bir yıllık baz primin o oranıdır — yine tavan üzerinden.\n\nAsıl mesele bundan sonrası ve çoğu kişinin beklemediği yer burası: **8. basamağa dönmek bir hasarsız yıl değil, 7. basamakta beş hasarsız sigorta süresi ister.** Diğer basamaklar arasında yılda bir kademe çıkılır; en üst basamağın kapısı ayrı bir kuralla açılır. Beş sigorta süresi boyunca 0,50 yerine 0,60 katsayısı işler. Her yılın farkı baz primin %10'u olduğuna göre beş yılın toplamı, BİR yıllık baz primin yarısı kadardır — beş yıllık primin yarısı değil. Bu hesap baz primin beş yıl boyunca sabit kaldığını varsayar; baz prim sabit kalmaz. Katsayılar tavan olduğu için çıkan sonuç da bir üst sınırdır, fiyat değil. En üst basamağı kaybetmek, \"bir basamak indi\" cümlesinin ima ettiğinden uzun sürer.\n\n**4. basamak nötr değildir.** Dolaşımdaki kaynakların çoğu hâlâ nötr yazar. Katsayısı 1,10, yani %10 artırım. Basamağı nötr kılan ifade 4/4/2023 değişikliğiyle metinden çıkarıldı; yanlış bilginin bu kadar yaygın olmasının sebebi tam olarak bu. Girişin 4. basamaktan olması da, ilk poliçenin nötr bir yerden değil %10 artırımlı bir tavandan başlaması demektir.\n\n**Ek-2 bir tavandır, fiyat değil.** Yönetmeliğin 5. maddesindeki indirim–artırım tablosu boş basılmıştır; oranların \"şirketlerce serbestçe belirlenecektir\" dediği yer orasıdır. Yani yukarıdaki katsayı azami primi bağlar. Şirket daha azını isteyebilir, fazlasını isteyemez. Poliçenizde uygulanan oran bu katsayının altında olabilir, üstünde olamaz. Poliçedeki lira tutarı ise baz prime bağlıdır; baz primi bu tablo belirlemez.\n\n**Kaskoda ulusal bir basamak sistemi yok.** Trafik sigortasının Ek-2'si gibi herkesi bağlayan bir kasko merdiveni hiç var olmadı. Kasko Genel Şartları C.11 hasarsızlık indirimini özel şart sayar ve yalnızca poliçede gösterilmesini ister: oran da, kademe sayısı da, hangi hasarın kademeyi düşürdüğü de şirketten şirkete değişir. Sizin için geçerli olan tek metin, kendi poliçenizde basılı olan klozdur. Kasko tarafını öğrenmenin yolu o klozu bulup okumaktır; buraya konulacak hiçbir tablo onun yerine geçmez.\n\nBir noktayı yine de bilmekte yarar var: yayımlanmış bir kasko klozunda **tam hasar (pert) ve çalınma, hasarsızlık indirimini kademe kademe düşürmüyor, tamamen sıfırlıyor.** Bu tek bir şirketin metnidir (Anadolu Sigorta KZ649 01/2024 §2.1.1), piyasa kuralı değildir — n=1. Ama kendi poliçenizde aynı hükmün olup olmadığına bakmaya değer, çünkü etkisi bir kademe değil, indirimin tümüdür.",
  caveat_tr: "Bu blok, bir ödeme yapıldıktan SONRASINI anlatır. Ödeme yapılıp yapılmayacağını, dolayısıyla basamağın gerçekten inip inmeyeceğini söylemez. Lira vermez: buradaki bütün yüzdeler baz prim üzerinedir; baz prim, basamak katsayısı uygulanmadan önceki yıllık primdir ve sizinkini burada bilmiyoruz. Poliçedeki lira tutarını Ek-2 belirlemez — Ek-2 yalnızca baz prime uygulanabilecek azami oranı bağlar, uygulanacak oran daha düşük olabilir; gerçek rakam ancak yenileme teklifinde görülür. Beş yıllık birikmiş farkın \"bir yıllık baz primin yarısı\" çıkması, baz primin beş yıl sabit kaldığı varsayımına dayanır; kalmaz. 0. ve 1. basamakların kendine özgü kuralları burada anlatılmamıştır. Kasko tarafında hiçbir oran verilmez — verilemez, çünkü ulusal bir tablo yoktur; geçerli olan yalnızca kendi poliçenizdeki klozdur. Bu blok aracın ağır hasarlı sayılıp sayılmayacağı, ödemenin tavanı, sovtaj ya da değer kaybı hakkında hiçbir şey söylemez.",
  citations: [
    {
        "text_tr": "Basamak katsayıları: 8 = 0,50 · 7 = 0,60 · 6 = 0,80 · 5 = 0,95 · 4 = 1,10 · 3 = 1,45 · 2 = 1,90 · 1 = 2,35 · 0 = 3,00. 15/4/2023'ten beri yürürlükte.",
        "source": "Karayolları Motorlu Araçlar Zorunlu Mali Sorumluluk Sigortası Tarife ve Talimatı, Ek-2 (RG 4/4/2023, No. 32153; yürürlük 15/4/2023)"
    },
    {
        "text_tr": "Sisteme giriş 4. basamaktan olur; hasarsız geçen her sigorta süresi bir basamak yukarı, her maddi hasar ödemesi bir basamak, her bedeni hasar ödemesi iki basamak aşağı taşır. Sayılan şey ödemedir, kaza değil.",
        "source": "Tarife ve Talimat, Geçici m.11(6), (7), (8)"
    },
    {
        "text_tr": "8. basamağa dönmek, 7. basamakta beş hasarsız sigorta süresi gerektirir.",
        "source": "Tarife ve Talimat, Geçici m.11(14)"
    },
    {
        "text_tr": "Madde 5'teki indirim–artırım tablosu boş basılmıştır: \"İndirim ve artırım oranları şirketlerce serbestçe belirlenecektir.\" Ek-2 oranları azami primi bağlar.",
        "source": "Tarife ve Talimat, m.5"
    },
    {
        "text_tr": "4. basamağı nötr kılan ifade 4/4/2023 tarihli değişiklikle Ek-2 metninden çıkarılmıştır; basamağın katsayısı 1,10'dur.",
        "source": "Tarife ve Talimat, Ek-2 (RG 4/4/2023, No. 32153)"
    },
    {
        "text_tr": "Kaskoda hasarsızlık indirimi bir özel şarttır; oranı ve kademeleri poliçede gösterilir, ulusal bir tablo yoktur.",
        "source": "Kara Araçları Kasko Sigortası Genel Şartları, C.11"
    },
    {
        "text_tr": "Tam hasar (pert) ve çalınma hâlinde hasarsızlık indiriminin tamamen sıfırlandığını öngören yayımlanmış bir kloz. Tek şirketin metnidir, piyasa kuralı değildir (n=1).",
        "source": "Anadolu Sigorta KZ649 01/2024, §2.1.1"
    }
],
};

export const PAYOUT_BLOCK: ClaimBlock = {
  order: 2,
  heading_tr: "Ne ödenebilir: tavanın nasıl kurulduğu bellidir, tutar değildir",
  body_tr: "**Tavan, kaza tarihindeki rayiç değer üzerinden kurulur.** Poliçeyi yaptırdığınız tarihteki değer değil, kazanın olduğu tarihteki rayiç değer esas alınır (Kasko Genel Şartları B.3-3.3.1.1).\n\n**Buradaki rakam listeye aittir, aracınıza değil.** Bu model için TSB Kasko Değer Listesi'nde yazan değer 1.584.880 TL. Bu, listenin model için yazdığı rakamdır; kilometre, donanım ve önceki hasar kaydı üzerinden yapılmış bireysel bir değerleme değildir. Mevzuat tavanı kurarken bu listeyi adres göstermez; tavanın dayanağı kaza tarihindeki rayiç değerdir ve o değer dosyada tespit edilir. Bu bloktaki bütün rakamlar liste değerinden türetilmiştir, ölçülmüş değildir.\n\n**Tarih farkı tavanın yerini değiştirir.** Aynı model 29 ay önceki TSB listesinde 1.225.751 TL yazıyordu. İki liste arasındaki fark 359.129 TL, yani %29,3. Poliçe tarihindeki rakam esas alınsaydı tavan bu kadar aşağıda kurulurdu. Kural sigortalının lehine yazılmış: esas alınan tarih kaza tarihidir. Bu karşılaştırma tarih seçiminin ne yaptığını gösterir; 359.129 TL'nin size ödeneceği anlamına gelmez. Poliçeniz bu listeden daha yeniyse karşılaştırma 29 ay üzerinden değil, kendi poliçe tarihiniz üzerinden kurulur.\n\n**Poliçedeki bedel rayicin altındaysa sorulacak soru tektir.** Genel şart tavanı kaza tarihindeki rayiç üzerinden kurar (Kasko Genel Şartları B.3-3.3.1.1). Poliçenizde yazan sigorta bedeli bugünkü rayicin altındaysa, dosyada hangi rakamın esas alındığı poliçenizin kendi maddesine bakılarak görülür. İki rakam farklıysa sorulacak soru şudur: dosyada hangi tarihin değeri esas alınmış?\n\n**Bundan sonrası yalnızca eşiğin üstünde kalınırsa gündeme gelir.** Enkaz, ancak araç ağır veya tam hasarlı sayılırsa konuşulur. Hangi tarafta olduğunuzu eksper raporu belirler; bu sistem KDV dahil onarım bedelini fotoğraftan hesaplayamaz.\n\n**Eşiğin üstünde hesap iki şekilde kurulur.** Enkaz teslim edilirse hesap tam rayiç üzerinden kurulur; bu yolda sovtaj indirimi gündeme gelmez. Enkaz sigortalıda kalırsa hesap \"rayiç eksi sovtaj\" olur. Sovtaj, hasarlı aracın enkaz değeridir ve tavandan düşülür. Her iki yolda da esas alınacak rayiç, kaza tarihi itibarıyla dosyada belirlenir; buradaki 1.584.880 TL modelin liste değeridir, dosyanın sonucu değildir. Hangi yolun işleyeceğini bu blok söylemiyor; enkazın kimde kalacağı poliçenin kendi hükümlerine göre işler.\n\n**Sovtaj burada hesaplanmıyor, çünkü hesaplanamaz.** Türkiye'de sovtaj/rayiç oranlarına dair yayımlanmış bir veri seti yok — ne kamu, ne sektör. Bu tutarı sigorta eksperi belirler ve verdiği rakamı bir ay geçerli tutar; bu iki cümlenin dayandığı bir düzenleme maddesi gösterilemiyor, kaynakçada da böyle yazıyor. Sistemin \"sovtaj yaklaşık şu kadardır\" demesi uydurma olurdu, o yüzden demiyor. Pratik sonucu şu: teslim yolunda bugün bilinen şey tavandır, ödenecek tutar değildir. Elinizde tutma yolunda ise tavandan ne düşüleceği ancak eksper sovtaj rakamını yazdığında belli olur. İki yolu gerçek anlamda o gün karşılaştırabilirsiniz. İki yolda da bugün bilinen şey tavandır.\n\n**Belge olmadan ödeme yok.** Mevzuat ödemeyi belgeye bağlar: tam hasarda hurda tescil belgesi, ağır hasarda \"trafikten çekilmiştir\" kaşeli tescil belgesi ibraz edilmeden ödeme yapılmaz (Kasko GŞ B.3-3.3.2.2; ZMSS GŞ B.2.3). Yani sıra ödemeye, aracın kaydına işlenen sonuçtan sonra gelir.\n\n**Hurdanın geri dönüşü yok, çekmenin var.** Hurdaya ayrılan araç bir daha tescil edilemez (Araçların Tescili Yönetmeliği m.44/6). Trafikten çekilen araç ise yeni muayene ve geçerli trafik sigortasıyla yeniden tescil edilebilir (m.43/2). Enkazı elinizde tutmayı düşünüyorsanız iki kayıt arasındaki fark budur: biri yeniden yola çıkabilecek bir araçtır, diğeri hiçbir koşulda değildir.\n\n**Değer kaybı ayrı bir dosyadır ve kayıt bu hakkı bitirir.** Değer kaybı, kaskonuzdan değil, kusurlu tarafın trafik sigortasından istenen ayrı bir taleptir. Araç ağır hasar veya hurda kaydı aldığı anda bu talep hakkı ortadan kalkar (Trafik Genel Şartları A.6/ö). Bu bir oran indirimi değil, hakkın tümüyle düşmesidir. Karşı taraf tamamen kusurlu olsa bile.\n\n**Borç ve şerhler ödemeyi kilitler.** MTV borcu, ödenmemiş trafik cezası, haciz veya rehin şerhi varken çekme/hurda kaydı yapılamaz; kayıt yapılamayınca ödeme de yapılamaz. Mevzuat bu tıkanma için bir yol yazmış: tutarın mahkemece belirlenen ödeme mahalline tevdii (SEDDK Genelge 2025/12 m.8/7). Maddenin varlığını bilmek bu yolun dosyada sorulabilmesini sağlar; yolun kendiliğinden işlediği anlamına gelmez.\n\n**Eşiğin altında kalınırsa araç sizden istenemez.** Tam veya ağır hasarlı sayılmayan araçlarda sigortacı, aracı hasarlı hâliyle kendisine ya da üçüncü kişilere terk ettiremez (SEDDK Genelge 2025/12 m.8/1). Nakit uzlaşma karşılığında araç talep edilirse bu hüküm sizin tarafınızdadır.\n\n**Neyi siz belirliyorsunuz, neyi belirlemiyorsunuz.** Sizde olan: borç ve şerhleri ne zaman temizleyeceğiniz; ağır hasar hâlinde aracı ileride yeniden tescil ettirip ettirmeyeceğiniz; poliçenizin sigorta bedeli ve enkaz maddelerini okuyup dosyada hangi tarihin değerinin esas alındığını sormanız. Sizde olmayan: hangi tarafta olduğunuz (eksper raporu belirler), sovtajın tutarı (eksper belirler), enkazın hangi yolda işleyeceği (poliçe hükümleri belirler), tavanın hangi tarihteki değerden kurulacağı (mevzuat belirler, kaza tarihi) ve kayıt işlendikten sonra değer kaybı hakkı (mevzuat düşürür).",
  caveat_tr: "Bu blok tek bir lira tutarını tahmin etmiyor. Ödenecek tazminatı, sovtajı ve değer kaybını söylemiyor; yalnızca tavanın hangi kurala göre kurulduğunu anlatıyor. Aracın ağır hasar veya tam hasar çizgisinin hangi tarafında kaldığını da söylemiyor — bunu yalnızca eksper raporu belirler ve bu sistem KDV dahil onarım bedelini fotoğraftan hesaplayamaz; enkazla ilgili bölümler ancak eşiğin üstünde kalınırsa anlam kazanır. 1.584.880 TL, model için TSB listesindeki değerdir; kilometre, donanım ve önceki hasar kaydı üzerinden yapılmış bir bireysel değerleme değildir ve mevzuatın tavan için adres gösterdiği bir kaynak da değildir. Bu rakamdan türetilen 950.928 TL'lik ağır hasar çizgisi ve 359.129 TL'lik tarih farkı da aynı sınırı taşır: türetilmiş rakamlardır, ölçülmüş değil. Blok, enkazın teslim mi edileceği yoksa sigortalıda mı kalacağı konusunda bir hak veya seçim taahhüt etmiyor; bunu poliçe hükümleri ve dosya belirler. Anlatılan tavan ve enkaz hesabı kasko kapsamındaki hasarı esas alır; karşı tarafın trafik sigortasından yürüyen dosyada teminat ve süreç farklıdır — değer kaybı da o dosyaya aittir, kaskoya değil. Prim ve basamak sonuçları bu blokta değil, sonraki blokta.",
  citations: [
    {
        "text_tr": "Tavan, aracın kaza tarihindeki rayiç değeri üzerinden kurulur; poliçenin yapıldığı tarihteki değer üzerinden değil.",
        "source": "Kasko Sigortası Genel Şartları B.3-3.3.1.1"
    },
    {
        "text_tr": "Bu model için TSB Kasko Değer Listesi'nde yazan değer 1.584.880 TL; 29 ay önceki listede 1.225.751 TL. Bu rakamlar listeye aittir: kilometre, donanım ve önceki hasar kaydı üzerinden yapılmış bireysel bir değerleme değildir. Liste, mevzuatın tavanı belirlemek için saydığı bir kaynak da değildir. Blokta liste değerinden türetilen her rakam da aynı şekilde türetilmiştir, ölçülmüş değildir.",
        "source": "TSB Kasko Değer Listesi (model değeri)"
    },
    {
        "text_tr": "Ağır hasar çizgisi, KDV dahil onarım masrafının aracın riziko tarihindeki değerinin %60'ını aşmasıdır. Yukarıdaki liste değeri üzerinden bu çizgi 950.928 TL'ye denk gelir; liste değeri bireysel bir değerleme olmadığı için çizgi de değerleme değiştiğinde birlikte değişir. Hangi tarafta olunduğunu eksper raporu belirler.",
        "source": "SEDDK Genelge 2025/12 m.5(1)"
    },
    {
        "text_tr": "Tam hasar için iki koşul birliktedir: KDV dahil onarım masrafının aracın değerinin tamamını aşması VE eksper raporuyla onarım kabul etmezliğin tespiti.",
        "source": "SEDDK Genelge 2025/12 m.4(1)"
    },
    {
        "text_tr": "Tam hasar ve ağır hasar tespitini yalnızca Levha'ya kayıtlı sigorta eksperi yapabilir. Bu maddeler sovtajı düzenlemez.",
        "source": "SEDDK Genelge 2025/12 m.4(2), m.5(2)"
    },
    {
        "text_tr": "Sovtaj: Türkiye'de yayımlanmış sovtaj/rayiç veri seti bulunamamıştır. Sovtajın kim tarafından ve nasıl belirleneceğine ve verilen rakamın bir ay geçerli tutulmasına ilişkin bir düzenleme atfı da verilememektedir.",
        "source": "Kaynak yok"
    },
    {
        "text_tr": "Tam hasarda hurda tescil belgesi, ağır hasarda \"trafikten çekilmiştir\" kaşeli tescil belgesi ibraz edilmeden ödeme yapılmaz.",
        "source": "Kasko GŞ B.3-3.3.2.2; ZMSS GŞ B.2.3"
    },
    {
        "text_tr": "Hurdaya ayrılan araç bir daha tescil edilemez; trafikten çekilen araç yeni muayene ve geçerli trafik sigortasıyla yeniden tescil edilebilir.",
        "source": "Araçların Tescili Yönetmeliği m.44/6 ve m.43/2"
    },
    {
        "text_tr": "Araç ağır hasar veya hurda kaydı aldığında değer kaybı tazminatı talep hakkı ortadan kalkar. Bu bir oran indirimi değil, hakkın tümüyle düşmesidir.",
        "source": "Karayolları Motorlu Araçlar Zorunlu Mali Sorumluluk Sigortası Genel Şartları A.6/ö (Ek: RG 4/12/2021-31679)"
    },
    {
        "text_tr": "MTV borcu, ödenmemiş trafik cezası, haciz veya rehin şerhi varken çekme/hurda kaydı yapılamaz. Mevzuatta yazılı yol: tutarın mahkemece belirlenen ödeme mahalline tevdii.",
        "source": "SEDDK Genelge 2025/12 m.8(7)"
    },
    {
        "text_tr": "Tam veya ağır hasarlı sayılmayan araçlarda sigortacı, aracı hasarlı hâliyle kendisine ya da üçüncü kişilere terk ettiremez.",
        "source": "SEDDK Genelge 2025/12 m.8(1)"
    },
    {
        "text_tr": "Bu sistemin genel hasar ağırlığı bandı %64,5 doğrulukta; en ağır bandın ölçülmüş yakalama oranı 0,51'dir ve hataların neredeyse tamamı bir bant DÜŞÜK yöndedir. KDV dahil onarım bedeli fotoğraftan hesaplanamaz.",
        "source": "BioVision iç değerlendirmesi (overall_severity)"
    }
],
};

export const WRITEOFF_BLOCK: ClaimBlock = {
  order: 3,
  heading_tr: "İki çizgi: değerin %60'ı ve tamamı",
  body_tr: "Bu ekran aracınızın değerini 1.584.880 TL olarak almıştır. Bu bir varsayımdır, tespit değildir — ve bir ödeme tutarı hiç değildir. Aşağıdaki iki çizgi yalnızca bu varsayılan değerin %60'ı ve tamamıdır. Mevzuatın ölçü aldığı değer ise aracın riziko tarihindeki — yani kaza günündeki — değeridir ve o değeri dosyada eksper belirler. Eksperin değeri farklı çıkarsa iki çizgi de birlikte kayar.\n\nMevzuat bu değerin üzerine iki çizgi çiziyor. İkisi de aynı şeye bakıyor: KDV dahil onarım masrafına.\n\n**Ağır hasar çizgisi: değerin %60'ı.** Varsayılan değerle 950.928 TL eder. KDV dahil onarım masrafı bu tutarı aşarsa araç ağır hasarlı sayılır. Karşılaştırmaya giren tutarı servisin teklifi değil, tespiti yapan eksperin raporu ortaya koyar. SEDDK Genelge 2025/12 m.5(1); 1 Temmuz 2025'ten beri yürürlükte.\n\n**Tam hasar çizgisi: değerin tamamı, artı bir rapor.** Varsayılan değerle 1.584.880 TL. Burada iki koşul birlikte aranır: KDV dahil onarım masrafının aracın değerinin tamamını aşması VE eksper raporuyla aracın onarım kabul etmez hâle geldiğinin tespiti. Rakamın tek başına aşılması yetmez; ikisi birden gerekir. m.4(1).\n\n**%70 diye bir eşik yoktur.** Bu konuda en çok tekrarlanan rakam budur ve hiçbir metinde karşılığı yoktur: ne Kasko Genel Şartları'nda, ne ZMSS Genel Şartları'nda, ne 2918 sayılı Karayolları Trafik Kanunu'nda, ne de tescil yönetmeliğinde. Mevzuattaki tek oran %60'tır.\n\n**Kesin olan orandır: %60.** Bu oranın lira karşılığı, eksperin belirleyeceği riziko tarihli değere göre değişir; ekranda gördüğünüz 950.928 TL, varsayılan değere göre hesaplanmış bir örnektir. Hangi tarafta olduğunuzu ise onarım bedeli belirler ve o bedel burada hesaplanmaz. Bu ekran fotoğraftan KDV dahil onarım bedelini hesaplamaz, çünkü bunu hesaplayabildiğini ölçmüş kimse yok. Fotoğraftan onarım maliyeti çıkardığını söyleyen hiçbir yöntemin gerçek onarım faturalarına karşı yayımlanmış bir doğruluk ölçümü bulunmuyor — ne akademide, ne Tractable, Solera, CCC ya da Mitchell'de. Bu şirketlerin yayımladığı sayılar işlem süresi ve otomasyon oranıdır; isabet değildir. Nedeni de teknik değil fizikseldir: bir onarımın gerektirdiği kalibrasyonların %51,5'i ancak parçalar söküldükten sonra ortaya çıkar. Fotoğraf sökümden öncedir.\n\n**Bu ekranın hasar bandı ne söyler, ne söylemez.** Band bir bedel değildir; bir olasılık da değildir. Ölçüm şudur: gerçekte en ağır bantta olan araçların yarısını (0,51) bu ekran o bantta işaretleyebiliyor. Bandın genel isabeti %64,5'tir ve hataların neredeyse tamamı bir bant AŞAĞI yöndedir. Yani bu ekranın hafif göstermesi, hasarın hafif olduğu anlamına gelmez.\n\n**İkinci yol: Ek-1.** Onarım masrafı %60 çizgisinin altında kalsa bile, Genelge'nin Ek-1 listesindeki 11 yapısal parçadan biri hasarlıysa eksper ağır hasar tespiti yapabilir. m.5(3). Maddenin lafzı \"yapılabilir\"dir; takdir ekspere aittir. SEDDK'nın basın duyurusu bu sonucu otomatikmiş gibi anlatır, Genelge'nin kendi metni ise takdire bırakır — iki metin aynı şeyi söylemiyor, burada Genelge'nin lafzı esas alınmıştır. Bu liste sizin açınızdan şu yüzden önemli: on bir kalemin sekizi panellerin arkasındadır ve bir dış fotoğrafta görünmez. Kalemlerin tam adları Genelge'nin Ek-1'inde yazılıdır; hasarlı parçanın listede olup olmadığını eksper söyler. Dokuzuncu sıradaki kalem hava yastıklarıdır. Onu da bir kamera göremez; ama siz bilirsiniz. Hava yastıklarının açılıp açılmadığı, ekspere söyleyeceğiniz ilk bilgilerden biridir.\n\n**Tespiti kim yapar.** Yalnızca Levha'ya kayıtlı bir sigorta eksperi. m.4(2), m.5(2). Servis de, bu ekran da bu tespiti yapamaz; ikisi de yalnızca eksperin bakacağı şeyleri hazırlar.\n\n**Eksperin rakamlarıyla geri dönün.** İki sayı gerekir ve ikisini de eksper verir: aracın riziko tarihindeki değeri ve KDV dahil onarım bedeli. Çizgiyi o değerden hesaplayın — değerin %60'ı ağır hasar çizgisidir. Sonra geriye hesap değil, karşılaştırma kalır: onarım bedeli bu çizginin altında mı, üstünde mi; aracın değerinin tamamını da aşıyor mu. Çizginin altındaysanız Ek-1 yolu ayrıca saklıdır. Çizginin üstündeki her tutar ağır hasar tarafındadır; bu tarafın üst sınırı yoktur. Tutar değerin tamamını da aşarsa, tam hasar için ikinci koşul — eksperin onarım kabul etmezlik raporu — ayrıca aranır; o rapor yoksa dosya tam hasar değil, ağır hasar olarak kalır. Tespiti her hâlde eksper yapar. m.5(1), m.4(1), m.4(2).\n\nEksperle konuşurken elinizde tutacağınız şey bir TL rakamı değil, orandır: ağır hasar çizgisi, aracın riziko tarihindeki değerinin %60'ıdır. Önce eksperin o tarih için belirlediği değeri öğrenin, çizgiyi o değerden hesaplayın.",
  caveat_tr: "Bu blok çizgilerin nereye düştüğünü söyler; aracınızın hangi tarafında olduğunu söylemez. Ekrandaki 1.584.880 TL bir tespit değil, hesabın dayandığı varsayımdır ve bir ödeme tutarı değildir; eksperin riziko tarihli değeri farklı çıkarsa buradaki iki lira rakamı da değişir. Onarım bedeli hesaplanmaz, dolayısıyla burada bir oran, bir olasılık veya bir sonuç yoktur. Eksperin Ek-1 takdirini kullanıp kullanmayacağı öngörülemez. Ödemenin tavanı, sovtaj, değer kaybı ve prim basamağı bu blokun konusu değildir.",
  citations: [
    {
        "text_tr": "Ağır hasar: KDV dahil onarım masrafının, aracın riziko tarihindeki değerinin %60'ını aşması.",
        "source": "SEDDK Genelge 2025/12 m.5(1); yürürlük 1/7/2025"
    },
    {
        "text_tr": "Tam hasar: KDV dahil onarım masrafının aracın değerinin tamamını aşması VE eksper raporuyla onarım kabul etmezlik tespiti. İki koşul birlikte aranır.",
        "source": "SEDDK Genelge 2025/12 m.4(1)"
    },
    {
        "text_tr": "Tespiti yalnızca Levha'ya kayıtlı bir sigorta eksperi yapar.",
        "source": "SEDDK Genelge 2025/12 m.4(2), m.5(2)"
    },
    {
        "text_tr": "%60'ın altında kalınsa bile, Ek-1 listesindeki 11 yapısal parçadan biri hasarlıysa eksper ağır hasar tespiti yapabilir; maddenin lafzı \"yapılabilir\"dir. Kalemlerin tam adları Ek-1'dedir; dokuzuncu sıradaki kalem hava yastıklarıdır.",
        "source": "SEDDK Genelge 2025/12 m.5(3) ve Ek-1"
    },
    {
        "text_tr": "Ek-1 yolunu SEDDK'nın basın duyurusu otomatik bir sonuç gibi anlatır; Genelge'nin lafzı ise eksperin takdirine bırakır. İki metin aynı şeyi söylemez; burada Genelge esas alınmıştır.",
        "source": "SEDDK basın duyurusu ile SEDDK Genelge 2025/12 m.5(3) karşılaştırması"
    },
    {
        "text_tr": "%70'lik bir eşik hiçbir metinde yoktur: ne Kasko Genel Şartları'nda, ne ZMSS Genel Şartları'nda, ne 2918 sayılı Karayolları Trafik Kanunu'nda, ne de tescil yönetmeliğinde. Mevzuattaki tek oran %60'tır.",
        "source": "SEDDK Genelge 2025/12 m.5(1); anılan diğer metinlerde karşılığı bulunmaması"
    },
    {
        "text_tr": "Bir onarımın gerektirdiği kalibrasyonların %51,5'i ancak parçalar söküldükten sonra ortaya çıkar.",
        "source": "Söküm sonrası ortaya çıkan kalibrasyonlara ilişkin sektör ölçümü"
    },
    {
        "text_tr": "Fotoğraftan KDV dahil onarım bedeli çıkardığını söyleyen hiçbir yöntemin gerçek onarım faturalarına karşı yayımlanmış doğruluk ölçümü yoktur; Tractable, Solera, CCC ve Mitchell yalnızca işlem süresi ve otomasyon oranı yayımlar.",
        "source": "Anılan sağlayıcıların yayımladığı metrikler; akademide karşılaştırmalı ölçüm bulunmaması"
    },
    {
        "text_tr": "Bu ekranın hasar bandı: genel isabet %64,5; en ağır bantta yakalama 0,51; hataların neredeyse tamamı bir bant aşağı yönde.",
        "source": "BioVision hasar bandı model değerlendirmesi"
    }
],
};

/** The states where the system has less to say, or nothing. */
export const STATES_BLOCK: ClaimBlock = {
  order: 0,
  heading_tr: "Üç ekran metni: değer girilmediğinde, değer girildiğinde ve her şeyin altında",
  body_tr: "**(a) Aracın değerini girmediyseniz**\n\nÇizgiler lira olarak yazılamıyor, çünkü ikisinin de paydası aracınızın değeri. Bu değer fotoğraftan çıkmaz: TSB Kasko Değer Listesi'nde 27.906 satır var ve tek bir markanın tek bir model yılı, motora ve şanzımana göre onlarca donanıma ayrılıyor. Bir görüntü modeli kaputun üstünden şanzıman okumaz.\n\nDeğer olmadan da değişmeyen şeyler var.\n\n**Ağır hasar çizgisi:** KDV dahil onarım masrafının, aracın kaza tarihindeki — mevzuattaki adıyla riziko tarihindeki — değerinin %60'ını aşması (SEDDK Genelge 2025/12 m.5(1); 1/7/2025'ten beri yürürlükte). Bu ekranda geçen \"kaza tarihindeki değer\" ile aynı değerdir, iki ayrı sayı değil.\n\n**Tam hasar çizgisi:** KDV dahil onarım masrafının değerin tamamını aşması **ve** eksper raporuyla aracın onarım kabul etmez hâle geldiğinin tespiti. İki şart birlikte aranır; biri tek başına yetmez (m.4(1)).\n\n**Yaygın söylenen %70'in hiçbir metinde karşılığı yok.** Ne Kasko Genel Şartları'nda, ne ZMSS Genel Şartları'nda, ne 2918 sayılı Kanun'da, ne tescil yönetmeliğinde. Mevzuattaki tek oran %60'tır (m.5(1)).\n\nTespiti yalnızca Levha'ya kayıtlı sigorta eksperi yapar (m.4(2), m.5(2)). Bu sistem yapmaz.\n\nBir de tarih meselesi: ödemenin tavanı, poliçe tarihindeki değil kaza tarihindeki rayiç değerdir (Kasko Genel Şartları B.3-3.3.1.1). Tavan, ödenecek tutar değildir; üst sınırdır, altındaki her tutar mümkündür. Bu tarih kuralının tavanı yukarı mı aşağı mı taşıdığı, aracın o iki tarih arasındaki piyasa değerine bağlıdır. Bu ekran tutar hesaplamaz.\n\nAğır hasar çizgisini lira olarak yazmak için tek bir sayı gerekir: aracın kaza tarihindeki değeri. Liste 15 model yılına kadar olan araçları kapsar; daha eskisi listede yoktur ve o değeri siz girersiniz. Tam hasar için lira cinsinden bir çizgi yazılamaz: m.4(1) parasal şartın yanında eksper raporuyla onarım kabul etmezlik tespitini de arar; bir sayının aşılması tek başına tam hasar sonucunu doğurmaz.\n\nAyrıca kaza sırasında hava yastıklarının açılıp açılmadığı sorulur. Bu soru çizgiyi oynatmaz. Hava yastıkları Ek-1 listesinin 9. kalemidir; %60'ın altında kalınsa bile Ek-1 yolundan ağır hasar tespiti yapılıp yapılmayacağı eksperin takdirindedir (m.5(3)). Bu ekran o değerlendirmeyi yapmaz; soru yalnızca fotoğrafta görünmeyen bir bilgiyi kayda geçirir.\n\n**(b) Değeri girdiniz ve fotoğraf {bant} bandına sınıflandı**\n\nFotoğrafın tamamına bakan değerlendirme bu kareyi **{bant}** bandına koydu. Bu bir tahmindir, ölçüm değil. 248 fotoğrafla test edildi: fotoğrafların %64,5'inde bandı doğru bildi. Ayrıca gerçekten ağır hasarlı olan fotoğrafların ancak %51'ini ağır bandına koyabildi — yani ağır hasarın yaklaşık yarısını olduğundan hafif okudu. (Bandınız orta ise buraya orta bandının oranı olan %45 gelir.) Bu sayılar mevzuattan gelmez; sistemin kendi test sonucudur.\n\nHatalar ağırlıklı olarak aşağı yönlü: gerçekte ağır hasarlı 91 fotoğrafın 37'si orta, 8'i az hasar okundu. Yani model hasarı olduğundan hafif okuma eğilimindedir ve bazen bir değil iki bant birden hafif okur. Bu bant hasarın üst sınırı değil, alt sınırı gibi okunmalı.\n\nBandı çizgiye çeviremiyoruz. Çizginin payı KDV dahil onarım bedelidir ve o bedel fotoğraftan çıkmaz. Gerçek onarım faturalarına karşı ölçülmüş doğruluğu yayımlanmış bir yöntem bulunamadı — ne akademik literatürde, ne Tractable, Solera, CCC veya Mitchell'de; onlar yalnızca süre ve otomasyon oranı yayımlıyor. Bu yüzden bu ekranda tahmini bir onarım bedeli yok, bantlı bir aralık da yok.\n\nÇizginin hangi tarafında kalınacağını üç şey belirler.\n\n**Parça seçimi.** Aynı hasar, hangi parçayla onarıldığına göre farklı tutar eder: orijinal parça, eşdeğer parça, yeniden kullanılabilir parça. Hangisinin uygulanacağını bu ekran bilmez; cevabı poliçenizin özel şartlarında aramak gerekir. Burada madde numarası verilmiyor, çünkü bu ekranın dayandığı mevzuat listesinde parça seçimine dair bir hüküm yok. Tutar bu seçimle değişir, dolayısıyla %60 çizgisinin hangi tarafında kalındığı da değişir.\n\n**Sökülmeden görünmeyen hasar.** Onarımın gerektirdiği ayar ve kalibrasyon işlemlerinin — sensör, kamera, direksiyon açısı gibi — %51,5'i ancak araç söküldükten sonra ortaya çıkıyor. Bu bir mevzuat hükmü değil, sektör verisidir; yukarıdaki %51 ile hiçbir ilgisi yoktur, ayrı bir sayıdır. Fotoğraf panelin arkasını görmez. Bu ekran onarım bedelini ne tahmin eder ne de yönünü söyler.\n\n**Ek-1 yolu.** %60'ın altında kalınsa bile, Ek-1 listesindeki 11 yapısal parçadan biri hasarlıysa eksper ağır hasar tespiti **yapabilir** (m.5(3)). İki resmî metin aynı şeyi söylemiyor: Genelge'nin kendi ifadesi \"yapılabilir\", yani takdir eksperdedir; SEDDK'nın basın duyurusu ise bunu otomatik bir sonuç gibi anlatıyor. Bu ekran dar olanı, takdire bağlı okumayı yazar. Sizin için pratik anlamı şu: Ek-1'deki bir parça hasarlıysa %60'ın altında da ağır hasar tespiti çıkabilir; çıkıp çıkmayacağını eksper belirler. Listedeki 11 kalemin 8'i panellerin arkasındadır ve fotoğrafta görünmez. 9. sıradaki kalem hava yastıklarıdır: fotoğraf bilmez, siz bilirsiniz.\n\nHangi tarafta olduğunuzu Levha'ya kayıtlı sigorta eksperi belirler (m.4(2), m.5(2)). O cevap bu ekranda yok.\n\n**(c) Her şeyin altında duran metin**\n\nBioVision sigorta şirketi değildir, acente değildir, sigorta eksperi değildir. Hiçbir ödeme taahhüdü vermez, hiçbir sigortacıyı bağlamaz. Ağır hasar ve tam hasar tespiti yalnızca Levha'ya kayıtlı sigorta eksperinin yetkisindedir (SEDDK Genelge 2025/12 m.4(2), m.5(2)). Hurda kaydı bunlardan ayrı bir tescil işlemidir ve bu ekranın konusu değildir.\n\nBu ekrandaki sayılar iki ayrı yerden gelir. Mevzuattan gelen çizgiler ve oranlar maddesiyle birlikte yazılır. Mevzuattan gelmeyenler — sistemin 248 fotoğrafla ölçülmüş doğruluk oranları, sektör verileri ve liste bilgileri — kaynağıyla ve mevzuat hükmü olmadıkları belirtilerek yazılır. Kaynağı gösterilemeyen sayı buraya yazılmaz.\n\nOnarım bedeli tahmin edilmez, sovtaj hesaplanmaz, değer kaybı lira olarak hesaplanmaz.",
  caveat_tr: "Bu üç metin, aracın çizginin hangi tarafında olduğunu söylemez; hiçbirinde lira cinsinden bir tazminat, onarım bedeli veya olasılık yoktur ve olmamalıdır. Ekran durumları artık girdiyle adlandırılıyor (\"değer girilmediğinde\", \"değer girildiğinde\"); \"çizgiye yakın\" gibi konum bildiren bir ad, bileşen adı veya rota adı kullanılmamalıdır, aksi hâlde kaldırılan iddia ürünün metin dışı kalan kısmında yaşamaya devam eder. Kapsamadıkları: prim/basamak ekranı (Ek-2, Geçici m.11) ve kasko hasarsızlık indirimi metni, ağır hasar kaydının değer kaybı hakkını tümüyle düşürmesi (KTK m.92(l)), hurda/çekme kayıtları ve haciz-MTV engeli — bunlar ayrı metinler ister. Kaynak notu: (b)'deki parça seçimi paragrafı bilerek maddesiz yazıldı ve maddesizliği metnin içinde açıkça söyleniyor; %51,5 sektör verisi, %64,5/%51/%45 ise bu deponun kendi ölçümüdür ve ikisi de mevzuat hükmü değildir. Yerleşim: frontend'de henüz claims arayüzü yok — /v1/claims uçları (C:\\Users\\bilal\\Desktop\\BioVision\\backend\\src\\biovision\\api\\routes\\claims.py) ekrana bağlı değil, dolayısıyla (a) ve (b) için bileşen yazılması gerekir; en yakın üslup örneği C:\\Users\\bilal\\Desktop\\BioVision\\frontend\\components\\ResultCard.tsx, (c) için doğal ev C:\\Users\\bilal\\Desktop\\BioVision\\frontend\\app\\kosullar\\page.tsx'teki \"Bu bir ekspertiz raporu değildir\" bölümüdür. (b)'deki {bant} bir yer tutucudur; gelen banda göre hem başlıktaki ad hem de yakalama oranı değişmelidir (ağır %51 / orta %45 / az hasar %98) ve parantez içindeki ikinci oran, gösterilmeyen bandın oranıdır — render ederken tek bir bandın sayısı bırakılmalıdır.",
  citations: [
    {
        "text_tr": "Ağır hasar: KDV dahil onarım masrafının aracın riziko tarihindeki değerinin %60'ını aşması. 1/7/2025'ten beri yürürlükte.",
        "source": "SEDDK Genelge 2025/12 m.5(1)"
    },
    {
        "text_tr": "Tam hasar: KDV dahil onarım masrafının değerin tamamını aşması VE eksper raporuyla onarım kabul etmezlik tespiti; iki şart birlikte aranır.",
        "source": "SEDDK Genelge 2025/12 m.4(1)"
    },
    {
        "text_tr": "Ağır hasar ve tam hasar tespitini yalnızca Levha'ya kayıtlı sigorta eksperi yapar.",
        "source": "SEDDK Genelge 2025/12 m.4(2), m.5(2)"
    },
    {
        "text_tr": "%60'ın altında kalınsa bile Ek-1'deki 11 yapısal parçadan biri hasarlıysa eksper ağır hasar tespiti yapabilir; lafız izinseldir, takdir eksperdedir.",
        "source": "SEDDK Genelge 2025/12 m.5(3) ve Ek-1"
    },
    {
        "text_tr": "Ödemenin tavanı, poliçe tarihindeki değil kaza (riziko) tarihindeki rayiç değerdir.",
        "source": "Kasko Genel Şartları B.3-3.3.1.1"
    },
    {
        "text_tr": "Bant sınıflandırmasının 248 held-out görselde genel doğruluğu %64,5; ağır bandı 91 örnekte %51 (37'si orta, 8'i az hasar okundu), orta bandı %45. Mevzuat hükmü değil, bu deponun kendi ölçümü.",
        "source": "README §7.8 (C:\\Users\\bilal\\Desktop\\BioVision\\README.md)"
    },
    {
        "text_tr": "Söküm yapılmadan görülemeyen hasar, gereken kalibrasyonların %51,5'ini oluşturuyor; bu yüzden onarım bedeli tahmin edilmez. Mevzuat hükmü değil, sektör verisi ve bir boşluğun gerekçesi.",
        "source": "regulation.yaml → unverified.repair_cost_from_photo (C:\\Users\\bilal\\Desktop\\BioVision\\backend\\src\\biovision\\domains\\regulation.yaml:347-354)"
    },
    {
        "text_tr": "Hurda tescili eksper tespiti değil, ayrı bir tescil işlemidir ve geri dönüşü yoktur.",
        "source": "Araçların Tescili Yönetmeliği m.44(6); 2918 s. KTK m.21 (regulation.yaml → consequences.hurda_irreversible)"
    }
],
};

/** Certainty order: the most solid number first. */
export const CLAIM_BLOCKS: ClaimBlock[] = [PREMIUM_BLOCK, PAYOUT_BLOCK, WRITEOFF_BLOCK];
