# J-REIT Intelligence v0.4

Property Intelligence Platform（PIP）の最初のモジュールです。NBF・JRE・GLPを横断し、地図、検索、物件詳細、時系列グラフ、類似物件比較、出典セル表示、CSV出力を備えます。

## データ方針

- 公開GitHubにはプログラムと架空データだけを置きます。
- NBF公式Excelの原本と変換後データはMac内だけに保存し、Git管理から除外します。
- 公式ファイルの「ご利用上の注意」と利用規約を確認し、許可のない再配布・転載を行わないでください。
- 数値は投資・融資判断に使用する前に原資料と照合してください。

## NBF実データのローカル取込（第40〜49期）

```bash
python3 scripts/import_nbf.py --accept-source-terms
```

原本を更新する場合：

```bash
python3 scripts/import_nbf.py --accept-source-terms --refresh
```

生成物は `data/properties.json` と `data/import-report.json` です。最新保有物件に過去10期のCAP、NOI、稼働率、鑑定評価額等を紐付けます。住所座標は国土地理院AddressSearchによる自動候補であり、建物位置の確認済み座標ではありません。

類似物件スコアは、距離35%、賃貸可能面積25%、取得価格15%、直接還元利回り15%、稼働率10%の簡易ロジックです。審査判断そのものではなく、比較候補を絞り込むために使用します。

## 3法人の横断取込

NBF・JRE・GLPをまとめて更新する場合：

```bash
python3 scripts/import_all.py --accept-source-terms
```

- NBF：70物件、第40〜49期
- JRE：79物件、直近10期（CRは公式Excelにないため空欄）
- GLP：85物件、第27〜28期（NOIは第28期）

原本を再取得する場合は `--refresh` を追加します。

## ローカル起動

```bash
python3 -m http.server 8000
```

ブラウザで <http://localhost:8000> を開きます。終了は `Control + C` です。

`data/properties.json` が存在しない場合は、架空データへ自動的に切り替わります。地図タイルとLeafletの表示にはネット接続が必要です。
