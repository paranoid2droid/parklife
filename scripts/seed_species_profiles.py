"""Seed curated species-level field-guide profiles for the demo modal.

This is intentionally small and human-readable. It gives the UI a real
species_profile data layer without pretending we have reviewed all 7k species.
Add profiles here gradually for common, high-impact species, then rerun:

    .venv/bin/python -m scripts.seed_species_profiles
    .venv/bin/python -m scripts.export_html
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from parklife import db

ROOT = Path(__file__).resolve().parent.parent


PROFILES_JA: dict[str, dict[str, str | list[str]]] = {
    "Hypsipetes amaurotis": {
        "summary": "公園でもっとも出会いやすい中型の鳥の一つです。よく通る声で鳴きながら、木の実、花の蜜、昆虫などを広く利用します。",
        "habitat_hint": "樹木の多い園路、林縁、実のなる木、花木の周辺。",
        "finding_tips": "まず声を聞き、木の上部や電線に止まる姿を探します。ツバキやサクラなど花のある時期は蜜を吸いに来ることがあります。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Streptopelia orientalis": {
        "summary": "林や住宅地に普通にいるハトで、首のしま模様が目印です。地面で種子を拾い、木の上で休みます。",
        "habitat_hint": "明るい林、芝生、園路脇、木立のある広場。",
        "finding_tips": "足元の草地や園路脇を静かに見てください。飛び立った後は近くの枝に止まることが多いです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Motacilla alba": {
        "summary": "白黒の体と長い尾を上下に振るしぐさが特徴です。開けた地面や水辺で小さな虫を探します。",
        "habitat_hint": "舗装路、芝生、池や川の縁、駐車場の周辺。",
        "finding_tips": "開けた場所を小走りで歩く鳥を探します。尾を振る動きが見えたらハクセキレイの可能性が高いです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Parus cinereus": {
        "summary": "黒いネクタイ模様が目立つ小鳥です。樹木を細かく移動しながら、虫や種子を探します。",
        "habitat_hint": "雑木林、園路沿いの木立、低木と高木が混じる場所。",
        "finding_tips": "小さな群れの声を聞いたら、枝先や幹の近くを追ってみてください。冬は他の小鳥と混群を作ることがあります。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Zosterops japonicus": {
        "summary": "目の周りの白い輪が名前の由来です。花の蜜や小さな果実を好み、枝の間をすばやく動きます。",
        "habitat_hint": "花木、実のなる木、常緑樹の茂み、公園の低木帯。",
        "finding_tips": "サクラ、ウメ、ツバキなどの花に来る小鳥を探します。体は小さいので、動きと声を先に見つけると楽です。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Passer montanus": {
        "summary": "人の暮らしの近くに多い小鳥です。草の種子や小さな虫を食べ、植え込みや建物周辺を利用します。",
        "habitat_hint": "広場、芝生、植え込み、売店や建物の周辺。",
        "finding_tips": "地面で群れている小鳥や、植え込みに出入りする姿を見てください。繁殖期は巣材を運ぶことがあります。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Anas zonorhyncha": {
        "summary": "都市公園の池でよく見られるカモです。水面で休み、水草や小動物を利用します。",
        "habitat_hint": "池、流れのゆるい川、岸辺の草地。",
        "finding_tips": "池の岸から水面を広く見渡してください。昼は休んでいることが多く、朝夕に動きが出ます。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Alcedo atthis": {
        "summary": "青く輝く体色が美しい水辺の鳥です。水面近くの枝や杭から小魚を狙います。",
        "habitat_hint": "池、川、湿地、見通しのよい水辺の枝や手すり。",
        "finding_tips": "水面をまっすぐ飛ぶ青い影を探します。同じ止まり場所に戻ることがあるので、見失っても少し待つ価値があります。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Trichonephila clavata": {
        "summary": "秋に大きな網を張る代表的なクモです。黄色と黒の体色が目立ち、林縁や園路脇でよく見つかります。",
        "habitat_hint": "林縁、低木の間、園路脇、明るい草地と木立の境目。",
        "finding_tips": "目線から少し上の高さにある大きな円網を探します。逆光だと網の糸が見えやすくなります。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Pseudozizeeria maha": {
        "summary": "小さな青いチョウで、都市公園でも普通に見られます。幼虫はカタバミ類を利用します。",
        "habitat_hint": "芝生の縁、園路脇、カタバミの生える明るい場所。",
        "finding_tips": "低い位置を小刻みに飛ぶ小さなチョウを探します。止まったら翅の裏の細かな斑点を確認してください。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Graptopsaltria nigrofuscata": {
        "summary": "夏の公園でよく鳴く大型のセミです。木の幹に止まり、朝から日中にかけて声が目立ちます。",
        "habitat_hint": "大きな樹木、街路樹、雑木林、日当たりのよい木立。",
        "finding_tips": "鳴き声の方向をたどり、幹の中ほどから上を探します。抜け殻は幹や低木、草の茎にも残ります。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Papilio xuthus": {
        "summary": "春から秋に見られる身近なアゲハチョウです。成虫は花を訪れ、幼虫はミカン科植物を利用します。",
        "habitat_hint": "花壇、明るい園路、ミカン科の植栽、草地の縁。",
        "finding_tips": "花の多い場所や柑橘類の植え込みを見てください。大型でゆったり飛ぶ黒黄のチョウが目印です。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Takydromus tachydromoides": {
        "summary": "草地や林縁で見られる細長いトカゲです。日なたで体を温め、危険を感じるとすばやく草むらに逃げます。",
        "habitat_hint": "草地の縁、低い植え込み、日当たりのよい石や木道の近く。",
        "finding_tips": "晴れた日に草の縁を静かに見てください。先に影を落とすと逃げやすいので、少し離れて観察します。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Bufo formosus": {
        "summary": "関東周辺で見られる大型のヒキガエルです。普段は林床や落ち葉の下に隠れ、繁殖期に水辺へ集まります。",
        "habitat_hint": "雑木林、湿った落ち葉、水辺近く、雨後の園路。",
        "finding_tips": "雨上がりの夕方や夜、林縁や水辺を探します。繁殖期以外は姿を見る機会が少なめです。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Armadillidium vulgare": {
        "summary": "丸くなることで知られる陸生の甲殻類です。落ち葉や石の下で湿った環境を好み、分解者として働きます。",
        "habitat_hint": "落ち葉、植え込みの根元、石や倒木の下、湿った花壇の縁。",
        "finding_tips": "石や落ち葉をそっと持ち上げて確認し、観察後は必ず元に戻します。乾いた日より湿った日の方が見つけやすいです。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Procambarus clarkii": {
        "summary": "池や水路で見られる外来のザリガニです。雑食性で、水草や小動物、落ち葉などさまざまなものを利用します。",
        "habitat_hint": "池、用水路、湿地の縁、泥底のある浅い水辺。",
        "finding_tips": "水際を静かにのぞき、泥底を歩く赤褐色の姿や巣穴を探します。水を濁らせないよう少し離れて観察します。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Geothelphusa dehaani": {
        "summary": "日本の淡水域にすむカニで、沢や湿った林内で見られます。水辺だけでなく、雨の日には陸上を歩くこともあります。",
        "habitat_hint": "沢沿い、湧水、湿った林床、石の多い水辺。",
        "finding_tips": "石のすき間や水際の落ち葉を静かに見てください。石を動かした場合は、観察後に必ず元に戻します。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Scaphechinus mirabilis": {
        "summary": "浅い砂地にすむ平たいウニの仲間です。公園データでは海辺や干潟に近い場所の記録として現れます。",
        "habitat_hint": "砂浜、干潟、浅い海の砂地、潮が引いた水辺。",
        "finding_tips": "干潮時に砂地の表面や打ち上げられた殻を探します。生きた個体は持ち帰らず、その場で観察してください。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Houttuynia cordata": {
        "summary": "湿った場所に多い多年草で、白い花びらのように見える部分が目立ちます。葉には独特の香りがあります。",
        "habitat_hint": "半日陰の湿った土、林縁、排水路沿い、植え込みの陰。",
        "finding_tips": "初夏は白い花序を目印に探します。花がない時期はハート形の葉と群生する姿が手がかりです。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Trifolium repens": {
        "summary": "芝生や広場で普通に見られるクローバーです。白い花はハチやチョウなど多くの昆虫を引き寄せます。",
        "habitat_hint": "芝生、広場、園路脇、踏みつけのある明るい草地。",
        "finding_tips": "足元の三小葉と白い丸い花を探します。花の周りを見ていると訪花昆虫も一緒に観察できます。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Lycoris radiata": {
        "summary": "秋に赤い花を咲かせる多年草です。花の時期には葉がなく、花後から冬にかけて細い葉を出します。",
        "habitat_hint": "林縁、土手、園路脇、やや湿った草地。",
        "finding_tips": "9月前後、赤い花がまとまって咲く場所を探します。開花期以外は見つけにくいので季節が重要です。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Ganoderma applanatum": {
        "summary": "枯れ木や弱った木に発生する硬い棚状の菌類です。多年生で、同じ場所に長く残ることがあります。",
        "habitat_hint": "倒木、古い切り株、弱った広葉樹の幹。",
        "finding_tips": "雨後だけでなく乾いた日にも見つかります。幹の側面に張り出す硬い半円形の子実体を探してください。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Cyprinus carpio": {
        "summary": "池やゆるい流れでよく見られる大型の淡水魚です。水面近くに出たり、泥底を探ったりします。",
        "habitat_hint": "公園の池、流れのゆるい水路、橋やデッキから見下ろせる水面。",
        "finding_tips": "水面の波紋や大きな影を探します。人影に寄ってくる個体もいますが、餌やりは禁止の場所では控えてください。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
    "Nyctereutes viverrinus": {
        "summary": "夜行性寄りの哺乳類で、雑木林や水辺のある都市近郊にも現れます。姿より足跡やため糞で気づくことがあります。",
        "habitat_hint": "林縁、草地、水辺、人気の少ない園路周辺。",
        "finding_tips": "早朝や夕方に静かな場所を観察します。野生動物なので近づきすぎず、餌を与えないでください。",
        "sources": ["iNaturalist", "Wikipedia"],
    },
}


def main() -> int:
    db_path = ROOT / "data" / "parklife.db"
    db.init(db_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted = 0
    missing = []
    with db.connect(db_path) as conn:
        for sci, profile in PROFILES_JA.items():
            row = conn.execute("SELECT id FROM species WHERE scientific_name=?", (sci,)).fetchone()
            if not row:
                missing.append(sci)
                continue
            conn.execute(
                """INSERT INTO species_profile
                   (species_id, lang, summary, habitat_hint, finding_tips, sources, updated_at)
                   VALUES (?, 'ja', ?, ?, ?, ?, ?)
                   ON CONFLICT(species_id, lang) DO UPDATE SET
                     summary=excluded.summary,
                     habitat_hint=excluded.habitat_hint,
                     finding_tips=excluded.finding_tips,
                     sources=excluded.sources,
                     updated_at=excluded.updated_at""",
                (
                    row["id"],
                    str(profile["summary"]),
                    str(profile["habitat_hint"]),
                    str(profile["finding_tips"]),
                    json.dumps(profile["sources"], ensure_ascii=False),
                    now,
                ),
            )
            inserted += 1
        conn.commit()
    print(f"upserted {inserted} ja species profiles")
    if missing:
        print("missing scientific names:")
        for sci in missing:
            print(f"  {sci}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
