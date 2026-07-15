# J-REIT Intelligence v0.5

Property Intelligence Platform（PIP）の最初のモジュールです。NBF・JRE・GLPを横断し、地図、検索、物件詳細、時系列グラフ、類似物件比較、出典セル表示、CSV出力を備えます。

## データ方針

- 公開GitHubにはコード、Schema、テスト、架空サンプルデータだけを置きます。
- 許諾済みJ-REIT実データ、原本PDF/Excel、正規化済みデータは`private-data/`へ保存し、Git管理から除外します。
- `private-data/`は現在のPoCではworktree内を既定とします。社内データ導入前に`PIP_PRIVATE_DATA_DIR`でworktree外または社内ストレージへ切り替えます。
- 公式ファイルの「ご利用上の注意」と利用規約を確認し、許可のない再配布・転載を行わないでください。
- 数値は投資・融資判断に使用する前に原資料と照合してください。

ローカル実データは次の構成です。ディレクトリ全体が`.gitignore`対象です。

```text
private-data/
├── raw/          原本Excel/PDF等
├── normalized/   正規化済みJSON
├── cache/        座標等のキャッシュ
├── reports/      取込・検証レポート
└── quarantine/   要確認データ
```

Git境界は次で確認できます。

```bash
python3 scripts/check_git_boundary.py
```

## NBF実データのローカル取込（第40〜49期）

```bash
python3 scripts/import_nbf.py --accept-source-terms
```

原本を更新する場合：

```bash
python3 scripts/import_nbf.py --accept-source-terms --refresh
```

生成物は`private-data/normalized/`、検証結果は`private-data/reports/`へ保存されます。最新保有物件に過去10期のCAP、NOI、稼働率、鑑定評価額等を紐付けます。住所座標は国土地理院AddressSearchによる自動候補であり、建物位置の確認済み座標ではありません。

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
python3 scripts/serve_local.py
```

ブラウザで <http://127.0.0.1:8000> を開きます。終了は`Control + C`です。サーバーはMac自身だけにbindし、`private-data/`、`sources/raw/`、旧実データパスへの直接アクセスを拒否します。画面へは`private-data/normalized/properties.json`だけを専用URL経由で渡します。

ローカル正規化データが存在しない場合は、`data/demo-properties.json`の架空データへ自動的に切り替わります。GitHub Pagesでは常に架空データ版として動作します。地図タイルとLeafletの表示にはネット接続が必要です。

## Evidence v1.0

各数値は`evidence`を持ち、次を記録します。

- metric code、値、単位、基準日
- 原本document ID、SHA-256、取得日時
- PDFページまたはExcelシート・セル
- Parser名、バージョン、抽出方法、confidence
- review status、確認者、確認日時

契約は`schema/source-evidence.schema.json`、`schema/canonical-property-period.schema.json`、`schema/metric-dictionary.json`です。現在のExcel ImporterはExcelシート・セルまで記録し、PDFページは今後のPDF Adapterで追加します。

## テスト

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_git_boundary.py
```
