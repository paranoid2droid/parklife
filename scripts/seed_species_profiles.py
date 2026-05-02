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
from urllib.parse import quote_plus

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
    "Corvus macrorhynchos": {
        "summary": "大きなくちばしと額の盛り上がりが目立つ都市公園の代表的なカラスです。雑食性で、木の実、小動物、人の活動に由来する食べ物も利用します。",
        "habitat_hint": "高木、広場、園路、池の周辺、売店やごみ置き場の近く。",
        "finding_tips": "太い声と大きな体を手がかりに探します。ハシボソガラスより額が高く、くちばしが太く見えます。繁殖期は巣に近づきすぎないでください。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Ardea cinerea": {
        "summary": "日本の公園で見られる大型のサギです。長い首と脚をもち、水辺で魚やカエル、小動物をじっと待って捕らえます。",
        "habitat_hint": "池、川、湿地、浅い水辺、岸辺の木や杭。",
        "finding_tips": "水際に立つ灰色の大きな鳥を探します。動きは少ないので、岸辺を広く見渡すと見つけやすいです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Corvus corone": {
        "summary": "開けた草地や農地、公園にも現れるカラスです。ハシブトガラスよりくちばしが細めで、額の段差がなだらかです。",
        "habitat_hint": "芝生、広場、川沿い、畑に近い公園、開けた園路。",
        "finding_tips": "地面を歩いて採食する姿を探します。近くにハシブトガラスがいれば、くちばしと頭の形を比べると識別しやすいです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Spodiopsar cineraceus": {
        "summary": "群れで行動することが多い都市公園の身近な鳥です。芝生や園路で虫や種子を探し、夕方には集団ねぐらへ向かいます。",
        "habitat_hint": "芝生、広場、低い草地、街路樹、建物周辺。",
        "finding_tips": "地面で群れて歩く黒っぽい鳥を探します。白い顔と橙色の脚が見えたらムクドリの可能性が高いです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Chloris sinica": {
        "summary": "黄色みのある翼が目立つ小鳥で、種子をよく食べます。群れで木の上や草地を移動することがあります。",
        "habitat_hint": "草地、林縁、実や種子の多い木、開けた園路沿い。",
        "finding_tips": "飛んだ時に翼の黄色い帯を確認します。冬は群れで見つかりやすく、木の上から声が聞こえることもあります。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Columba livia": {
        "summary": "都市部で非常に身近なハトです。公園の広場や建物周辺を利用し、地面で種子や落ちた食べ物を探します。",
        "habitat_hint": "広場、駅や建物に近い公園、橋の下、舗装された園路。",
        "finding_tips": "群れで歩く姿を探します。野生由来ではなく都市環境に適応した個体が多いので、餌やりは避けて観察します。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Phalacrocorax carbo": {
        "summary": "黒い体で水中に潜って魚を捕る大型の水鳥です。休む時は杭や木の上で翼を広げることがあります。",
        "habitat_hint": "大きめの池、川、海辺に近い水域、杭や中洲。",
        "finding_tips": "水面に低く浮かぶ黒い鳥や、潜った後に少し離れて浮上する姿を探します。翼を広げて乾かす姿も目印です。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Hirundo rustica": {
        "summary": "春から夏にかけて見られる身近なツバメです。空中で小さな昆虫を捕り、建物や橋の近くで繁殖します。",
        "habitat_hint": "開けた広場、水辺、建物の軒下、橋や管理施設の周辺。",
        "finding_tips": "低くすばやく飛ぶ細い翼の鳥を探します。雨前や水辺では低空を飛ぶことが多く、尾の長い形が手がかりです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Phoenicurus auroreus": {
        "summary": "冬に公園へやってくる小鳥で、雄は橙色の腹と黒い顔が目立ちます。開けた場所の低い枝や杭から虫を探します。",
        "habitat_hint": "林縁、低木、畑や草地の縁、フェンスや杭のある場所。",
        "finding_tips": "尾を細かく震わせる小鳥を探します。同じ止まり場所に戻ることがあるので、少し待つと観察しやすいです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Turdus eunomus": {
        "summary": "冬に芝生や林床でよく見られるツグミ類です。地面を数歩歩いて止まる動きを繰り返し、ミミズや実を探します。",
        "habitat_hint": "芝生、明るい林床、落ち葉のある広場、実のなる木の下。",
        "finding_tips": "地面で胸を張って立ち止まる鳥を探します。冬から早春に見つけやすく、落ち葉をめくる音も手がかりです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Egretta garzetta": {
        "summary": "白い体と黒い脚、黄色い足先が特徴の小型のサギです。浅い水辺を歩きながら魚や小動物を捕ります。",
        "habitat_hint": "池や川の浅瀬、湿地、水路、干潟に近い水辺。",
        "finding_tips": "白いサギを見つけたら足先の黄色を確認します。水際を歩き回る個体は採食中で、動きを観察しやすいです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Anas platyrhynchos": {
        "summary": "世界的に広く見られるカモで、公園の池でも観察しやすい鳥です。水面で休み、水草や小動物を利用します。",
        "habitat_hint": "池、流れの緩い川、岸辺の草地、人工池。",
        "finding_tips": "池の岸から水面をゆっくり見渡します。雄は緑色の頭が目立ちますが、雌や若鳥は褐色で周囲に溶け込みます。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Lanius bucephalus": {
        "summary": "小さな猛禽のような習性をもつ鳥で、昆虫や小動物を捕ります。秋冬の公園では低木や杭の上に止まる姿が目立ちます。",
        "habitat_hint": "草地の縁、低木、開けた林縁、フェンスや杭のある場所。",
        "finding_tips": "見晴らしのよい低い枝や杭に単独で止まる鳥を探します。尾を回すように動かすしぐさも手がかりです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Anas crecca": {
        "summary": "小型のカモで、冬に池や湿地で見られます。水面や浅瀬で植物質の餌を探します。",
        "habitat_hint": "池、湿地、浅い水辺、流れのゆるい川。",
        "finding_tips": "ほかのカモより小さい個体を探します。岸近くや草の陰にいることが多いので、双眼鏡があると見つけやすいです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Ardea alba": {
        "summary": "白い大型のサギで、長い首と脚が目立ちます。浅い水辺で魚や小動物を待ち伏せします。",
        "habitat_hint": "池、川、湿地、干潟に近い浅い水辺。",
        "finding_tips": "遠くからでも白く大きな姿が目立ちます。コサギより大きく、脚全体が黒っぽく見えることが多いです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Yungipicus kizuki": {
        "summary": "日本の公園でも出会いやすい小型のキツツキです。幹や枝を移動しながら、樹皮のすき間の昆虫を探します。",
        "habitat_hint": "雑木林、古い木の多い園路、林縁、枯れ枝のある木立。",
        "finding_tips": "細い鳴き声や軽いドラミング音を聞いたら、幹や枝を下から上へ移動する小鳥を探します。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Horornis diphone": {
        "summary": "春のさえずりで有名な小鳥ですが、姿は藪の中に隠れがちです。虫を食べ、低木や笹の多い場所を利用します。",
        "habitat_hint": "藪、笹、低木の多い林縁、湿った谷筋。",
        "finding_tips": "春は声を頼りに探します。姿を見るには、声のする藪の縁で静かに待ち、動く影を追うのが近道です。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Milvus migrans": {
        "summary": "空を旋回する大型の猛禽です。海岸や川、公園上空でも見られ、死肉や魚、人の食べ物由来のものも利用します。",
        "habitat_hint": "海や川に近い公園、広い空が見える場所、上昇気流の出る斜面や広場。",
        "finding_tips": "空を見上げ、翼を広げて輪を描く大きな鳥を探します。尾が浅く二股に見えることがあります。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Cyanopica cyanus": {
        "summary": "長い尾と青い翼が美しいカラスの仲間です。群れで行動し、林縁や住宅地に近い公園にも現れます。",
        "habitat_hint": "明るい林、林縁、園路沿いの高木、住宅地に近い緑地。",
        "finding_tips": "にぎやかな群れの声を聞いたら、木の中ほどから上を探します。飛ぶと長い尾と青い翼がよく目立ちます。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
    "Emberiza personata": {
        "summary": "冬の藪や林縁でよく見られるホオジロ類です。地面や低い草の間で種子を探します。",
        "habitat_hint": "藪、草地の縁、林床、落ち葉のある低木帯。",
        "finding_tips": "地面近くで小さく動く鳥を探します。驚くと近くの枝に上がることがあるので、飛んだ先を追うと確認しやすいです。",
        "sources": ["eBird", "iNaturalist", "Wikipedia"],
    },
}


PROFILES_EN_ZH: dict[str, dict[str, dict[str, str]]] = {
    "Hypsipetes amaurotis": {
        "en": {"summary": "One of the easiest medium-sized birds to meet in parks. It uses fruit, nectar, and insects, often announcing itself with a carrying call.", "habitat_hint": "Tree-lined paths, woodland edges, fruiting trees, and flowering trees.", "finding_tips": "Listen first, then scan the upper branches and wires. Around camellias and cherry blossoms it may visit flowers for nectar."},
        "zh": {"summary": "公园里最容易遇到的中型鸟类之一。叫声响亮，会利用果实、花蜜和昆虫等多种食物。", "habitat_hint": "树木较多的园路、林缘、结果树和开花树附近。", "finding_tips": "先听声音，再看树冠和电线上停着的鸟。山茶、樱花等开花时也可能来吸蜜。"},
    },
    "Streptopelia orientalis": {
        "en": {"summary": "A common dove of woods and neighborhoods, recognizable by the striped patch on the neck. It feeds on seeds on the ground and rests in trees.", "habitat_hint": "Open woodland, lawns, path edges, and plazas with trees.", "finding_tips": "Check lawns and path edges quietly. If one flushes, it often lands again on a nearby branch."},
        "zh": {"summary": "常见于树林和居民区的鸠鸽类，颈部条纹是明显特征。常在地面啄食种子，也会在树上休息。", "habitat_hint": "明亮树林、草坪、园路边和有树木的广场。", "finding_tips": "安静观察脚边草地和园路边。飞起后常会落到附近树枝上。"},
    },
    "Motacilla alba": {
        "en": {"summary": "A black-and-white wagtail with a long tail that bobs up and down. It hunts tiny insects in open ground and along water edges.", "habitat_hint": "Paved paths, lawns, pond and stream edges, and parking areas.", "finding_tips": "Look for a bird trotting across open ground. The tail-bobbing motion is the giveaway."},
        "zh": {"summary": "黑白相间、长尾上下摆动的小鸟。常在开阔地面和水边寻找小昆虫。", "habitat_hint": "铺装路、草坪、池塘或河流边缘、停车场附近。", "finding_tips": "寻找在开阔地小跑的鸟。看到不断摆尾，往往就是白鹡鸰。"},
    },
    "Parus cinereus": {
        "en": {"summary": "A small bird with a bold black tie-like mark. It moves busily through trees, searching for insects and seeds.", "habitat_hint": "Woodlots, tree-lined paths, and mixed shrubs and tall trees.", "finding_tips": "When you hear a small flock, follow movement along branch tips and trunks. In winter it often joins mixed flocks."},
        "zh": {"summary": "胸前有黑色领带状花纹的小鸟。会在树间快速移动，寻找昆虫和种子。", "habitat_hint": "杂木林、园路旁树木、灌木和高树混合的地方。", "finding_tips": "听到小鸟群的声音后，沿枝梢和树干寻找。冬季常和其他小鸟混群。"},
    },
    "Zosterops japonicus": {
        "en": {"summary": "A tiny bird named for its white eye-ring. It likes nectar and small fruit and moves quickly through dense branches.", "habitat_hint": "Flowering trees, fruiting trees, evergreen shrubs, and low plantings.", "finding_tips": "Check plum, cherry, camellia, and other flowers. It is small, so movement and calls are the easiest clues."},
        "zh": {"summary": "因眼周白圈得名的小鸟。喜欢花蜜和小果实，常在枝叶间快速移动。", "habitat_hint": "开花树、结果树、常绿树丛和低矮灌木。", "finding_tips": "留意梅、樱、山茶等花木。个体很小，先找动作和叫声更容易。"},
    },
    "Passer montanus": {
        "en": {"summary": "A familiar bird of human surroundings. It eats grass seeds and small insects and uses shrubs and buildings.", "habitat_hint": "Plazas, lawns, hedges, shops, and building edges.", "finding_tips": "Watch for small flocks on the ground or birds moving in and out of hedges. In breeding season they may carry nest material."},
        "zh": {"summary": "常在人类生活环境附近出现的小鸟。吃草籽和小昆虫，也利用灌丛和建筑周边。", "habitat_hint": "广场、草坪、绿篱、售店和建筑附近。", "finding_tips": "观察地面成群的小鸟，或进出灌丛的个体。繁殖期可能会搬运巢材。"},
    },
    "Anas zonorhyncha": {
        "en": {"summary": "A duck often seen on urban park ponds. It rests on open water and feeds on aquatic plants and small animals.", "habitat_hint": "Ponds, slow rivers, and grassy banks.", "finding_tips": "Scan the water from the bank. They often rest by day and become more active in the morning and evening."},
        "zh": {"summary": "城市公园池塘中常见的鸭类。会在水面休息，也取食水草和小型动物。", "habitat_hint": "池塘、缓流河段和岸边草地。", "finding_tips": "从岸边环视水面。白天常在休息，清晨和傍晚活动更多。"},
    },
    "Alcedo atthis": {
        "en": {"summary": "A bright blue waterside bird that hunts small fish from branches, railings, or posts near the water.", "habitat_hint": "Ponds, streams, wetlands, and exposed perches by water.", "finding_tips": "Look for a blue flash flying straight over the water. It may return to the same perch, so wait after a sighting."},
        "zh": {"summary": "体色鲜蓝的水边鸟类，会从枝条、栏杆或木桩上俯冲捕小鱼。", "habitat_hint": "池塘、溪流、湿地和水边视野开阔的停歇点。", "finding_tips": "寻找贴水直飞的蓝色影子。它常回到同一停歇点，看到后可以等一等。"},
    },
    "Trichonephila clavata": {
        "en": {"summary": "A large orb-weaving spider most noticeable in autumn. Its yellow-and-black body and large web stand out along woodland edges.", "habitat_hint": "Woodland edges, gaps between shrubs, path edges, and sunny grass-tree boundaries.", "finding_tips": "Search for large round webs slightly above eye level. Backlight often makes the web threads easier to see."},
        "zh": {"summary": "秋季很显眼的大型结网蜘蛛，黄黑体色和大圆网常出现在林缘和园路旁。", "habitat_hint": "林缘、灌木间、园路边、草地与树丛交界处。", "finding_tips": "寻找略高于视线的大型圆网。逆光时蛛丝更容易看见。"},
    },
    "Pseudozizeeria maha": {
        "en": {"summary": "A tiny blue butterfly common even in urban parks. Its larvae use wood sorrels and related plants.", "habitat_hint": "Lawn edges, path edges, and sunny places with wood sorrel.", "finding_tips": "Look low for a small butterfly fluttering close to the ground. When it lands, check the fine spots on the underside."},
        "zh": {"summary": "城市公园也常见的小型蓝色蝴蝶，幼虫利用酢浆草等植物。", "habitat_hint": "草坪边、园路旁、有酢浆草的明亮地方。", "finding_tips": "寻找贴近地面小幅飞行的小蝶。停下后可观察翅背面的细小斑点。"},
    },
    "Graptopsaltria nigrofuscata": {
        "en": {"summary": "A large cicada whose calls define summer parks. Adults sit on tree trunks and are most obvious from morning through daytime.", "habitat_hint": "Large trees, roadside trees, woodlots, and sunny tree stands.", "finding_tips": "Follow the call and scan the middle to upper trunk. Empty shells may remain on trunks, shrubs, and grass stems."},
        "zh": {"summary": "夏季公园里叫声很突出的较大型蝉。成虫停在树干上，清晨到白天较明显。", "habitat_hint": "大树、行道树、杂木林和向阳树丛。", "finding_tips": "顺着鸣声寻找树干中上部。蜕壳也可能留在树干、灌木和草茎上。"},
    },
    "Papilio xuthus": {
        "en": {"summary": "A familiar swallowtail seen from spring to autumn. Adults visit flowers, and larvae use citrus-family plants.", "habitat_hint": "Flower beds, bright paths, citrus plantings, and grass edges.", "finding_tips": "Check flower-rich spots and citrus shrubs. Its large yellow-and-black flight is easy to notice."},
        "zh": {"summary": "春到秋都容易见到的常见凤蝶。成虫访花，幼虫利用芸香科植物。", "habitat_hint": "花坛、明亮园路、柑橘类植栽和草地边缘。", "finding_tips": "观察花多的地方和柑橘类灌木。黄黑相间的大型蝴蝶飞行很醒目。"},
    },
    "Takydromus tachydromoides": {
        "en": {"summary": "A slender lizard of grasslands and woodland edges. It warms itself in sunny spots and darts into vegetation when disturbed.", "habitat_hint": "Grass edges, low shrubs, sunny stones, and boardwalk edges.", "finding_tips": "On sunny days, watch grass margins quietly from a little distance. Avoid casting a shadow over it."},
        "zh": {"summary": "常见于草地和林缘的细长蜥蜴。会在向阳处晒太阳，受惊后迅速钻入草丛。", "habitat_hint": "草地边缘、低矮灌木、向阳石头和木道附近。", "finding_tips": "晴天安静观察草丛边缘。距离稍远，避免影子先落到它身上。"},
    },
    "Bufo formosus": {
        "en": {"summary": "A large toad of the Kanto region. It usually hides on the forest floor or under leaf litter and gathers at water for breeding.", "habitat_hint": "Woodlots, damp leaf litter, watersides, and paths after rain.", "finding_tips": "After rain, search woodland edges and watersides in the evening. Outside breeding season it is harder to see."},
        "zh": {"summary": "关东周边可见的大型蟾蜍。平时多藏在林床或落叶下，繁殖期会聚集到水边。", "habitat_hint": "杂木林、潮湿落叶层、水边和雨后园路。", "finding_tips": "雨后傍晚或夜间，在林缘和水边寻找。繁殖期以外较难见到。"},
    },
    "Armadillidium vulgare": {
        "en": {"summary": "A land crustacean famous for rolling into a ball. It prefers damp places under leaves and stones and helps break down organic matter.", "habitat_hint": "Leaf litter, hedge bases, under stones or logs, and damp flower-bed edges.", "finding_tips": "Lift leaves or stones gently, then put them back after observing. Damp days are better than dry ones."},
        "zh": {"summary": "会卷成球的陆生甲壳类。喜欢落叶和石头下的潮湿环境，也是重要的分解者。", "habitat_hint": "落叶层、植丛根部、石头或倒木下、潮湿花坛边缘。", "finding_tips": "轻轻翻看石头或落叶，观察后务必放回原处。潮湿天气比干燥天气更容易找到。"},
    },
    "Procambarus clarkii": {
        "en": {"summary": "An introduced crayfish found in ponds and channels. It is omnivorous, using aquatic plants, small animals, and leaf litter.", "habitat_hint": "Ponds, irrigation channels, wetland edges, and shallow muddy water.", "finding_tips": "Look quietly along the water edge for reddish-brown bodies or burrows in mud. Keep some distance to avoid stirring the water."},
        "zh": {"summary": "池塘和水路中可见的外来螯虾，杂食，会利用水草、小动物和落叶等。", "habitat_hint": "池塘、用水路、湿地边缘和有泥底的浅水处。", "finding_tips": "安静查看水边，寻找红褐色个体或泥中的洞穴。保持距离，避免把水搅浑。"},
    },
    "Geothelphusa dehaani": {
        "en": {"summary": "A freshwater crab of Japan, found around streams and damp woodland. On rainy days it may walk away from the water.", "habitat_hint": "Streams, springs, damp forest floor, and stony watersides.", "finding_tips": "Check gaps between stones and leaf litter near water quietly. If you move a stone, put it back after observing."},
        "zh": {"summary": "日本淡水域中的蟹类，常在溪流和潮湿林地附近出现。雨天也可能离开水边活动。", "habitat_hint": "溪流、涌水、潮湿林床和石头多的水边。", "finding_tips": "安静查看石缝和水边落叶。若移动石头，观察后请放回原处。"},
    },
    "Scaphechinus mirabilis": {
        "en": {"summary": "A flat sand-dollar-like sea urchin that lives in shallow sandy areas. Park records usually point to coastal or tidal-flat settings.", "habitat_hint": "Sandy beaches, tidal flats, shallow sandy sea bottom, and exposed shore at low tide.", "finding_tips": "At low tide, look on sandy surfaces or for washed-up tests. Observe living individuals in place and do not take them home."},
        "zh": {"summary": "生活在浅海砂地中的扁平海胆类。公园记录通常来自靠海或干潟环境。", "habitat_hint": "沙滩、干潟、浅海砂底和退潮后的水边。", "finding_tips": "退潮时寻找砂地表面或被冲上岸的壳。活体请原地观察，不要带走。"},
    },
    "Houttuynia cordata": {
        "en": {"summary": "A perennial herb of damp places. The white petal-like bracts stand out, and the leaves have a distinctive scent.", "habitat_hint": "Damp soil in partial shade, woodland edges, drains, and shaded plantings.", "finding_tips": "In early summer, look for the white flower heads. Outside flowering season, heart-shaped leaves and dense patches are clues."},
        "zh": {"summary": "常见于潮湿处的多年生草本。白色花瓣状部分很醒目，叶子有独特气味。", "habitat_hint": "半阴的潮湿土壤、林缘、排水沟旁和植丛阴处。", "finding_tips": "初夏可用白色花序寻找。不开花时，看心形叶和成片生长的状态。"},
    },
    "Trifolium repens": {
        "en": {"summary": "A familiar clover of lawns and open ground. Its white flowers attract bees, butterflies, and many other insects.", "habitat_hint": "Lawns, plazas, path edges, and bright trampled grass.", "finding_tips": "Look for three leaflets and round white flower heads. Watching the flowers can also reveal visiting insects."},
        "zh": {"summary": "草坪和广场常见的三叶草。白色花序会吸引蜂、蝶等多种昆虫。", "habitat_hint": "草坪、广场、园路边和被踩踏的明亮草地。", "finding_tips": "寻找三出复叶和白色圆形花序。观察花周围，还能看到访花昆虫。"},
    },
    "Lycoris radiata": {
        "en": {"summary": "A perennial that flowers red in autumn. Leaves are absent while it blooms and appear after flowering through winter.", "habitat_hint": "Woodland edges, banks, path edges, and slightly damp grass.", "finding_tips": "Around September, search for clusters of red flowers. Season matters because it is much harder to notice outside bloom."},
        "zh": {"summary": "秋季开红花的多年生植物。开花时没有叶，花后到冬季会长出细长叶。", "habitat_hint": "林缘、土坡、园路边和稍湿的草地。", "finding_tips": "9月前后寻找成片红花。花期外较难发现，季节非常关键。"},
    },
    "Ganoderma applanatum": {
        "en": {"summary": "A hard bracket fungus that grows on dead or weakened trees. It is perennial and can remain in the same place for a long time.", "habitat_hint": "Fallen logs, old stumps, and weakened broadleaf trunks.", "finding_tips": "It can be found even on dry days. Look for hard semicircular shelves projecting from trunks."},
        "zh": {"summary": "生长在枯木或衰弱树木上的坚硬层孔菌。多年生，可能长期留在同一位置。", "habitat_hint": "倒木、旧树桩和衰弱阔叶树树干。", "finding_tips": "不只雨后，干燥天气也能找到。留意树干侧面伸出的坚硬半圆形子实体。"},
    },
    "Cyprinus carpio": {
        "en": {"summary": "A large freshwater fish often seen in ponds and slow water. It may surface or forage along muddy bottoms.", "habitat_hint": "Park ponds, slow channels, and water visible from bridges or decks.", "finding_tips": "Look for ripples or large shadows near the surface. Do not feed them where feeding is prohibited."},
        "zh": {"summary": "池塘和缓流水域中常见的大型淡水鱼。会靠近水面，也会在泥底觅食。", "habitat_hint": "公园池塘、缓流水路、桥或平台下方的水面。", "finding_tips": "寻找水面波纹或大型影子。禁止投喂的地方请不要喂食。"},
    },
    "Nyctereutes viverrinus": {
        "en": {"summary": "A mostly nocturnal mammal that can appear in suburban woods and watersides. Tracks and latrine sites are often easier to notice than the animal itself.", "habitat_hint": "Woodland edges, grassland, watersides, and quiet paths.", "finding_tips": "Try early morning or evening in quiet areas. Keep distance and never feed wild mammals."},
        "zh": {"summary": "偏夜行性的哺乳动物，也会出现在城市近郊的林地和水边。足迹和固定排便点有时比本体更容易发现。", "habitat_hint": "林缘、草地、水边和人少的园路周边。", "finding_tips": "清晨或傍晚在安静地点观察。请保持距离，不要投喂野生动物。"},
    },
    "Corvus macrorhynchos": {
        "en": {"summary": "A large-billed crow that is very common in urban parks. It is omnivorous, using fruit, small animals, and food linked to human activity.", "habitat_hint": "Tall trees, plazas, paths, watersides, and areas near shops or bins.", "finding_tips": "Listen for the deep call and look for a large crow with a heavy bill and high forehead. Avoid nest areas in breeding season."},
        "zh": {"summary": "城市公园里常见的大嘴乌鸦，嘴粗、额头隆起明显。杂食，会利用果实、小动物和人类活动相关的食物。", "habitat_hint": "高树、广场、园路、水边、售店或垃圾点附近。", "finding_tips": "先听低沉叫声，再找体型大、嘴粗的乌鸦。繁殖期请不要靠近巢区。"},
    },
    "Ardea cinerea": {
        "en": {"summary": "A large heron often seen in Japanese parks. It waits patiently at watersides to catch fish, frogs, and small animals.", "habitat_hint": "Ponds, rivers, wetlands, shallow water, waterside trees, and posts.", "finding_tips": "Scan broadly for a tall grey bird standing at the edge of water. It often moves very little, so slow looking helps."},
        "zh": {"summary": "日本公园水边常见的大型鹭类，长颈长脚，会静候鱼、蛙和小动物。", "habitat_hint": "池塘、河流、湿地、浅水边、岸边树木和木桩。", "finding_tips": "沿水边寻找灰色大型鸟。它常常几乎不动，慢慢扫视更容易发现。"},
    },
    "Corvus corone": {
        "en": {"summary": "A crow of open lawns, farmland edges, and parks. Compared with the large-billed crow, the bill is slimmer and the forehead is smoother.", "habitat_hint": "Lawns, plazas, riversides, open paths, and parks near fields.", "finding_tips": "Look for crows feeding on the ground. If large-billed crows are nearby, compare bill thickness and head shape."},
        "zh": {"summary": "常见于开阔草地、农地边缘和公园的乌鸦。与大嘴乌鸦相比，嘴较细、额头较平缓。", "habitat_hint": "草坪、广场、河边、开阔园路和靠近农地的公园。", "finding_tips": "寻找在地面觅食的乌鸦。附近若有大嘴乌鸦，可比较嘴和头部轮廓。"},
    },
    "Spodiopsar cineraceus": {
        "en": {"summary": "A familiar park bird that often moves in flocks. It feeds on insects and seeds on lawns and paths and may gather at roosts in the evening.", "habitat_hint": "Lawns, plazas, low grass, roadside trees, and building edges.", "finding_tips": "Watch for dark birds walking together on the ground. A pale face and orange legs are useful clues."},
        "zh": {"summary": "常成群活动的熟悉公园鸟类，会在草坪和园路上寻找昆虫与种子，傍晚可能集群归巢。", "habitat_hint": "草坪、广场、低草地、行道树和建筑周边。", "finding_tips": "寻找在地面成群行走的黑色鸟。白脸和橙色脚是重要线索。"},
    },
    "Chloris sinica": {
        "en": {"summary": "A small seed-eating bird with yellow wing patches. It may move in flocks between trees and open grassy areas.", "habitat_hint": "Grassland, woodland edges, seed-rich trees, and open paths.", "finding_tips": "Check for yellow bands in the wings when it flies. In winter, flocks and calls from treetops make it easier to find."},
        "zh": {"summary": "带黄色翼斑的小型食籽鸟，会成群在树上和开阔草地间移动。", "habitat_hint": "草地、林缘、种子多的树和开阔园路。", "finding_tips": "飞起时注意翅上的黄色带。冬季群体和树冠上的叫声更容易提供线索。"},
    },
    "Columba livia": {
        "en": {"summary": "A very familiar pigeon of urban areas. It uses plazas and building edges and feeds on seeds and fallen food on the ground.", "habitat_hint": "Plazas, parks near stations or buildings, under bridges, and paved paths.", "finding_tips": "Look for flocks walking on open ground. Observe without feeding, especially where feeding pigeons is discouraged."},
        "zh": {"summary": "城市里非常常见的鸽类，常利用广场和建筑周边，在地面寻找种子和掉落食物。", "habitat_hint": "广场、靠近车站或建筑的公园、桥下和铺装园路。", "finding_tips": "寻找在开阔地行走的鸽群。观察即可，请避免投喂。"},
    },
    "Phalacrocorax carbo": {
        "en": {"summary": "A large black waterbird that dives for fish. When resting, it may spread its wings on posts or trees.", "habitat_hint": "Large ponds, rivers, coastal waters, posts, and small islands.", "finding_tips": "Look for a dark bird floating low, diving, then resurfacing some distance away. Wing-spreading is another strong clue."},
        "zh": {"summary": "大型黑色水鸟，会潜水捕鱼。休息时常在木桩或树上张开翅膀。", "habitat_hint": "较大的池塘、河流、近海水域、木桩和小洲。", "finding_tips": "寻找低浮在水面的黑色鸟，潜水后会在较远处浮出。张翼晾干也很醒目。"},
    },
    "Hirundo rustica": {
        "en": {"summary": "A swallow seen from spring to summer. It catches tiny insects in the air and often nests near buildings or bridges.", "habitat_hint": "Open plazas, watersides, building eaves, bridges, and park facilities.", "finding_tips": "Watch for fast, low flight with narrow wings and a forked tail. Before rain and near water it often flies low."},
        "zh": {"summary": "春夏常见的燕子，会在空中捕食小昆虫，也常在建筑和桥附近繁殖。", "habitat_hint": "开阔广场、水边、屋檐、桥和公园设施周边。", "finding_tips": "寻找低空快速飞行、翅窄尾叉的鸟。雨前和水边常飞得更低。"},
    },
    "Phoenicurus auroreus": {
        "en": {"summary": "A winter visitor to parks. Males show an orange belly and dark face, and both sexes hunt from low perches.", "habitat_hint": "Woodland edges, shrubs, field edges, fences, and posts.", "finding_tips": "Look for a small bird that quivers its tail. It often returns to the same perch, so waiting can pay off."},
        "zh": {"summary": "冬季来到公园的小鸟，雄鸟橙色腹部和黑脸明显，常从低枝或木桩上捕虫。", "habitat_hint": "林缘、灌木、田地边缘、围栏和木桩。", "finding_tips": "寻找会轻轻抖尾的小鸟。它常回到同一停歇点，等一会儿更容易观察。"},
    },
    "Turdus eunomus": {
        "en": {"summary": "A winter thrush often seen on lawns and forest floors. It walks a few steps, pauses upright, then searches for worms and fruit.", "habitat_hint": "Lawns, bright forest floor, leafy plazas, and under fruiting trees.", "finding_tips": "Watch the ground for a bird that walks and stops with an upright posture. Winter to early spring is best."},
        "zh": {"summary": "冬季常在草坪和林床出现的鸫类，会走几步后直立停顿，寻找蚯蚓和果实。", "habitat_hint": "草坪、明亮林床、有落叶的广场和结果树下。", "finding_tips": "观察地面上走走停停、姿态较直的鸟。冬季到早春最容易遇到。"},
    },
    "Egretta garzetta": {
        "en": {"summary": "A small white heron with black legs and yellow feet. It walks through shallow water catching fish and small animals.", "habitat_hint": "Shallow pond or river edges, wetlands, channels, and tidal watersides.", "finding_tips": "When you see a white egret, check for yellow feet. Actively walking birds are often feeding and easy to watch."},
        "zh": {"summary": "小型白色鹭类，黑脚配黄色脚趾，会在浅水中行走捕食鱼和小动物。", "habitat_hint": "池塘或河流浅水边、湿地、水路和近潮汐水边。", "finding_tips": "看到白鹭时注意黄色脚趾。来回走动的个体多在觅食，便于观察。"},
    },
    "Anas platyrhynchos": {
        "en": {"summary": "A widespread duck that is easy to observe on park ponds. It rests on water and feeds on aquatic plants and small animals.", "habitat_hint": "Ponds, slow rivers, grassy banks, and artificial ponds.", "finding_tips": "Scan the water slowly from the bank. Males have a green head, while females and young birds are mottled brown."},
        "zh": {"summary": "分布广、在公园池塘容易观察的鸭类，会在水面休息并取食水草和小动物。", "habitat_hint": "池塘、缓流河段、岸边草地和人工池。", "finding_tips": "从岸边慢慢扫视水面。雄鸟绿头明显，雌鸟和幼鸟为褐色斑驳。"},
    },
    "Lanius bucephalus": {
        "en": {"summary": "A songbird with raptor-like habits, catching insects and small animals. In autumn and winter it often perches on shrubs or posts.", "habitat_hint": "Grassland edges, shrubs, open woodland edges, fences, and posts.", "finding_tips": "Look for a solitary bird on a low exposed perch. Tail movements and a hooked bill are helpful clues."},
        "zh": {"summary": "习性像小型猛禽的鸣禽，会捕食昆虫和小动物。秋冬常停在灌木或木桩上。", "habitat_hint": "草地边缘、灌木、开阔林缘、围栏和木桩。", "finding_tips": "寻找单独停在低处显眼位置的鸟。尾部动作和略钩的嘴是线索。"},
    },
    "Anas crecca": {
        "en": {"summary": "A small duck seen on ponds and wetlands in winter. It feeds on plant material at the surface and in shallow water.", "habitat_hint": "Ponds, wetlands, shallow water, and slow rivers.", "finding_tips": "Look for ducks smaller than the others, often near banks or vegetation. Binoculars help because they can stay partly hidden."},
        "zh": {"summary": "冬季在池塘和湿地可见的小型鸭类，会在水面和浅水处取食植物质。", "habitat_hint": "池塘、湿地、浅水区和缓流河段。", "finding_tips": "寻找比其他鸭子更小的个体，常在岸边或水草附近。用望远镜更容易确认。"},
    },
    "Ardea alba": {
        "en": {"summary": "A large white heron with long legs and neck. It waits in shallow water for fish and small animals.", "habitat_hint": "Ponds, rivers, wetlands, tidal flats, and shallow watersides.", "finding_tips": "Its large white body is visible from far away. It is larger than a little egret and often looks long-legged and all-white."},
        "zh": {"summary": "大型白色鹭类，长颈长脚，会在浅水中等待鱼和小动物。", "habitat_hint": "池塘、河流、湿地、干潟和浅水边。", "finding_tips": "远处也能看到它醒目的大型白色身影。比小白鹭更大，腿和颈显得更长。"},
    },
    "Yungipicus kizuki": {
        "en": {"summary": "A small woodpecker that is fairly easy to meet in Japanese parks. It searches bark and branches for insects.", "habitat_hint": "Woodlots, older trees, woodland edges, and trees with dead branches.", "finding_tips": "Listen for thin calls or light drumming, then scan trunks and branches for a small bird moving upward."},
        "zh": {"summary": "日本公园里较容易遇到的小型啄木鸟，会沿树干和枝条寻找树皮缝中的昆虫。", "habitat_hint": "杂木林、老树多的园路、林缘和有枯枝的树木。", "finding_tips": "听到细声或轻微啄木声后，沿树干和枝条寻找向上移动的小鸟。"},
    },
    "Horornis diphone": {
        "en": {"summary": "Famous for its spring song but often hidden in dense vegetation. It feeds on insects in shrubs and bamboo grass.", "habitat_hint": "Thickets, bamboo grass, shrubby woodland edges, and damp valleys.", "finding_tips": "In spring, use the song as your guide. Wait quietly at the edge of the thicket and watch for movement."},
        "zh": {"summary": "以春季鸣唱闻名，但本体常藏在密丛中。会在灌木和竹草间取食昆虫。", "habitat_hint": "灌丛、竹草、低木多的林缘和潮湿谷地。", "finding_tips": "春季先靠声音定位，在灌丛边安静等待，注意移动的影子。"},
    },
    "Milvus migrans": {
        "en": {"summary": "A large raptor often seen circling in the sky. It uses coastal and riverside areas and may scavenge fish or food scraps.", "habitat_hint": "Parks near the sea or rivers, open skies, slopes, and wide plazas.", "finding_tips": "Look upward for a large bird circling with broad wings. The tail can look shallowly forked."},
        "zh": {"summary": "常在天空盘旋的大型猛禽，常利用海边和河边环境，也会取食鱼或残食。", "habitat_hint": "靠海或河流的公园、视野开阔的天空、斜坡和大广场。", "finding_tips": "抬头寻找张开宽翼盘旋的大鸟。尾部有时看起来浅浅分叉。"},
    },
    "Cyanopica cyanus": {
        "en": {"summary": "A crow relative with a long tail and blue wings. It moves in noisy groups through woodland edges and suburban parks.", "habitat_hint": "Open woods, woodland edges, tall trees along paths, and green spaces near housing.", "finding_tips": "When you hear a lively group, scan the middle and upper tree levels. The long tail and blue wings stand out in flight."},
        "zh": {"summary": "长尾、蓝翼很漂亮的鸦科鸟类，常成群在林缘和住宅地附近公园活动。", "habitat_hint": "明亮树林、林缘、园路旁高树和靠近住宅的绿地。", "finding_tips": "听到热闹群声后，查看树的中上层。飞行时长尾和蓝色翅膀很明显。"},
    },
    "Emberiza personata": {
        "en": {"summary": "A bunting often found in winter thickets and woodland edges. It searches for seeds on the ground and in low grass.", "habitat_hint": "Thickets, grass edges, forest floor, and low shrubs with leaf litter.", "finding_tips": "Look for small movements close to the ground. If it flushes, follow it to a nearby branch for a better view."},
        "zh": {"summary": "冬季常见于灌丛和林缘的鹀类，会在地面和低草间寻找种子。", "habitat_hint": "灌丛、草地边缘、林床和有落叶的低木带。", "finding_tips": "寻找贴近地面的小动作。受惊飞起后常落到附近枝条上，跟过去更容易确认。"},
    },
}


ZH_T_REPLACEMENTS = {
    "动物": "動物", "鸟": "鳥", "鱼": "魚", "类": "類", "贝": "貝", "软": "軟",
    "体": "體", "线": "線", "边": "邊", "园": "園", "树": "樹", "丛": "叢",
    "湿": "濕", "叶": "葉", "处": "處", "见": "見", "时": "時", "会": "會",
    "声": "聲", "从": "從", "来": "來", "个": "個", "这": "這", "为": "為",
    "种": "種", "发": "發", "现": "現", "与": "與", "节": "節", "较": "較",
    "长": "長", "场": "場", "开": "開", "关": "關", "东": "東", "间": "間",
    "后": "後", "义": "義", "带": "帶", "纹": "紋", "单": "單", "无": "無",
    "紧": "緊", "还": "還", "对": "對", "应": "應", "让": "讓", "数": "數",
    "处": "處", "边": "邊", "这": "這", "请": "請", "远": "遠", "动": "動",
    "浑": "濁", "浅": "淺", "层": "層", "连": "連", "阳": "陽", "阴": "陰",
    "鲜": "鮮", "蓝": "藍", "条": "條", "栏": "欄", "杆": "桿", "桩": "樁", "冲": "衝",
    "虾": "蝦", "杂": "雜",
    "飞": "飛", "猎": "獵", "猎": "獵", "识": "識", "绕": "繞", "处": "處",
    "产": "產", "业": "業", "经": "經", "营": "營", "卫": "衛", "观": "觀",
    "察": "察", "寻找": "尋找", "现": "現", "湿": "濕", "干": "乾",
    "迹": "跡", "粪": "糞", "龄": "齡", "变": "變", "称": "稱", "显": "顯",
    "圆": "圓", "叶": "葉", "丛": "叢", "类": "類", "为": "為", "声": "聲",
    "过": "過", "发": "發", "开": "開", "关": "關", "张": "張", "较": "較",
    "线": "線", "带": "帶", "纹": "紋", "轻": "輕", "质": "質", "请": "請",
    "应": "應", "变": "變", "许": "許", "临": "臨", "义": "義", "独": "獨",
}


def zh_to_zh_t(text: str) -> str:
    for src, dst in ZH_T_REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text


def ensure_profile_schema(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(species_profile)")}
    if "source_urls" not in cols:
        conn.execute("ALTER TABLE species_profile ADD COLUMN source_urls TEXT")


def wikipedia_url(common_name_ja: str | None, sci: str) -> str:
    query = common_name_ja or sci
    return f"https://ja.wikipedia.org/wiki/Special:Search?search={quote_plus(query)}"


def source_url_records(conn, species_id: int, sci: str, common_name_ja: str | None, sources: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if "Wikipedia" in sources:
        rows.append({"label": "Wikipedia", "url": wikipedia_url(common_name_ja, sci)})
    if "iNaturalist" in sources:
        taxon = conn.execute("SELECT inat_taxon_id FROM species WHERE id=?", (species_id,)).fetchone()
        if taxon and taxon["inat_taxon_id"]:
            rows.append({"label": "iNaturalist", "url": f"https://www.inaturalist.org/taxa/{taxon['inat_taxon_id']}"})
        else:
            rows.append({"label": "iNaturalist", "url": f"https://www.inaturalist.org/search?q={quote_plus(sci)}"})
    if "eBird" in sources:
        eb = conn.execute(
            "SELECT raw_name FROM species_alias WHERE species_id=? AND lang='ebird' LIMIT 1",
            (species_id,),
        ).fetchone()
        if eb and eb["raw_name"]:
            rows.append({"label": "eBird", "url": f"https://ebird.org/species/{eb['raw_name']}"})
        else:
            rows.append({"label": "eBird", "url": f"https://ebird.org/search?query={quote_plus(sci)}"})
    return rows


def profile_variants(sci: str, ja_profile: dict[str, str | list[str]]) -> dict[str, dict[str, str | list[str]]]:
    variants: dict[str, dict[str, str | list[str]]] = {"ja": ja_profile}
    translated = PROFILES_EN_ZH.get(sci, {})
    for lang in ("en", "zh"):
        if lang in translated:
            variants[lang] = {**ja_profile, **translated[lang]}
    if "zh" in translated:
        variants["zhT"] = {
            **ja_profile,
            "summary": zh_to_zh_t(translated["zh"]["summary"]),
            "habitat_hint": zh_to_zh_t(translated["zh"]["habitat_hint"]),
            "finding_tips": zh_to_zh_t(translated["zh"]["finding_tips"]),
        }
    return variants


def main() -> int:
    db_path = ROOT / "data" / "parklife.db"
    db.init(db_path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted = 0
    missing = []
    with db.connect(db_path) as conn:
        ensure_profile_schema(conn)
        for sci, profile in PROFILES_JA.items():
            row = conn.execute(
                "SELECT id, common_name_ja FROM species WHERE scientific_name=?",
                (sci,),
            ).fetchone()
            if not row:
                missing.append(sci)
                continue
            sources = list(profile["sources"])
            source_urls = source_url_records(conn, row["id"], sci, row["common_name_ja"], sources)
            for lang, localized in profile_variants(sci, profile).items():
                conn.execute(
                    """INSERT INTO species_profile
                       (species_id, lang, summary, habitat_hint, finding_tips,
                        sources, source_urls, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(species_id, lang) DO UPDATE SET
                         summary=excluded.summary,
                         habitat_hint=excluded.habitat_hint,
                         finding_tips=excluded.finding_tips,
                         sources=excluded.sources,
                         source_urls=excluded.source_urls,
                         updated_at=excluded.updated_at""",
                    (
                        row["id"],
                        lang,
                        str(localized["summary"]),
                        str(localized["habitat_hint"]),
                        str(localized["finding_tips"]),
                        json.dumps(sources, ensure_ascii=False),
                        json.dumps(source_urls, ensure_ascii=False),
                        now,
                    ),
                )
                inserted += 1
        conn.commit()
    print(f"upserted {inserted} localized species profiles")
    if missing:
        print("missing scientific names:")
        for sci in missing:
            print(f"  {sci}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
