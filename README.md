# 政策金利盤

主要11通貨（USD / EUR / JPY / GBP / AUD / NZD / CAD / CHF / ZAR / TRY / MXN）の政策金利と
全ペアの金利差を、スマホから固定URLで見るための個人用ダッシュボード。

- ホスティング：GitHub Pages（無料・静的）
- 自動更新：GitHub Actions が毎日 BIS のAPIを叩いて `data/rates.json` を更新
- サーバー不要。Mac mini の電源が入っていなくても動く

---

## 1. リポジトリを作る

GitHub で新しいリポジトリを作る（例：`policy-rate-board`）。**Public** にすること。
Private だと GitHub Pages は有料プラン扱いになる。

このフォルダの中身をそのまま push する。

```bash
cd policy-rate-board
git init -b main
git add .
git commit -m "政策金利盤 初期コミット"
git remote add origin https://github.com/<ユーザー名>/policy-rate-board.git
git push -u origin main
```

## 2. Pages を有効にする

リポジトリの **Settings → Pages** で

- Source: `Deploy from a branch`
- Branch: `main` / `/ (root)`

を選んで保存。1〜2分で URL が出る。

```
https://<ユーザー名>.github.io/policy-rate-board/
```

これが毎回叩くURL。ブックマークするならこれ。

## 3. 自動更新を有効にする

**Settings → Actions → General → Workflow permissions** を
`Read and write permissions` にして保存。
（Actions が `data/rates.json` をコミットし返すのに必要）

**Actions** タブ →「政策金利を更新」→ `Run workflow` で手動実行し、
緑になれば成功。以降は毎日 06:20 JST 前後に自動で走る。

> スケジュール実行は GitHub 側の混雑で数十分〜1時間ずれることがある。
> また、リポジトリに60日間まったくコミットがないと schedule が自動停止するので、
> その場合は Actions タブから一度手動実行すれば再開する。

## 4. スマホのホーム画面に置く

- **iPhone（Safari）**：URLを開く → 共有ボタン → 「ホーム画面に追加」
- **Android（Chrome）**：URLを開く → 右上の︙ → 「アプリをインストール」

アドレスバーのないアプリのように開く。オフラインでも前回取得分は表示される。

---

## 次回会合の日程を更新する

`meetings.json` に各中銀の予定を書いてあります。日付が過ぎたものは自動で読み飛ばされるので、
消す必要はありません。**年末に翌年分を追記する**運用です。

```json
"USD": {
  "cb": "FOMC",
  "calendar": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
  "meetings": [
    { "date": "2027-01-27", "time": "4:00 JST", "label": "1/26-27会合" }
  ]
}
```

必須は `date` だけ。`time` と `label` は任意です。push すれば即反映されます
（会合日程は画面側で直接読むので、Actions の実行を待つ必要はありません）。

### 未登録の通貨について

**ZAR・TRY・MXN は 2026年後半の確定日程を確認できなかったため空欄**にしてあります。
画面下部に公式カレンダーへのリンクが出るので、確認して追記してください。
また毎日の Actions は、今後の予定が尽きた通貨をログに警告として出します。

```
[warn] 今後の会合日程が未登録: ZAR, TRY, MXN → meetings.json に追記してください
```

### 収録済みの日程（2026年8月15日確認）

| 通貨 | 残りの2026年予定 | 確認元 |
|---|---|---|
| USD | 9/17・10/29・12/10（日本時間の声明発表日） | FRB公表の年間日程 |
| JPY | 9/18・10/30・12/18 | 日銀 |
| EUR | 9/10・10/29・12/17 | ECB理事会日程 |
| GBP | 9/17・11/5・12/17 | BOE公表の2026年日程 |
| AUD | 9/29・11/3・12/8 | RBA公表の2026年日程 |
| NZD | 9/2・10/28・12/9 | RBNZ公表の日程 |
| CAD | 9/2・10/28・12/9 | BOC公表の2026年日程 |
| CHF | 9/24・12/10 | 四半期政策評価 |

---

## 会合直後に手で直したいとき

BIS は各中銀の発表を反映するまで数日かかることがある。
日銀やFOMCの直後にすぐ盤面を直したいときは `overrides.json` を書き換えて push する。

```json
{
  "JPY": { "rate": 1.25, "changed_on": "2026-09-19", "note": "9月会合で0.25%利上げ" }
}
```

push すると Actions が走り、その通貨だけ手動値が優先される（盤面に「手動更新」と出る）。
BIS が追いついたら、その項目を消して push すれば自動値に戻る。

---

## ファイル構成

```
index.html                        画面（スマホ優先レイアウト）
sw.js                             オフライン用 Service Worker
manifest.webmanifest              ホーム画面追加用
data/rates.json                   Actions が生成する金利データ
overrides.json                    金利の手動上書き
meetings.json                     会合日程（画面が直接読む）
scripts/fetch_rates.py            BIS から取得する（標準ライブラリのみ）
.github/workflows/update-rates.yml  毎日実行
```

ローカルで確認するときは、`file://` だと fetch が動かないので簡易サーバーを立てる。

```bash
python3 -m http.server 8000
# http://localhost:8000/ を開く
```

## データについて

- 一次データ：[BIS Central bank policy rates (WS_CBPOL)](https://www.bis.org/statistics/cbpol.htm)
- 米FF金利はレンジ目標のため中央値。ECB は BIS の採用系列に従う（MRO / DFR の違いに注意）
- BIS の利用条件は [Terms of permitted use of BIS statistics](https://www.bis.org/terms_use.htm) を参照

日本語の速報性なら [トレーダーズ・ウェブFX](https://www.traderswebfx.jp/interest_rate/) の方が早いが、
同サイトは第三者への再配信を禁じているため、公開ページの自動取得元には使っていない。
手元で確認して `overrides.json` に反映する使い方なら問題ない。

## 免責

金利差はスワップの方向感を掴むための材料であって、それ単体では売買根拠にならない。
表示値の正確性は保証しない。実際の判断の前に各中央銀行の発表を確認すること。
