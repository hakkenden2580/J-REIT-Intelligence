# J-REIT Intelligence v0.10

Property Intelligence Platform（PIP）の最初のモジュールです。NBF・JRE・GLPを横断し、地図、検索、物件詳細、時系列グラフ、類似物件比較、出典セル表示、CSV出力を備えます。v0.6でData Engine契約、v0.7でData Quality Gate、v0.8でデータ差分検出、v0.9でPDF共通基盤、v0.10でNBF決算説明会資料の法人別PDF Adapterを追加しました。

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
├── quarantine/   要確認データ
└── snapshots/    正常データの圧縮履歴（最大12世代）
```

Git境界は次で確認できます。

```bash
python3 scripts/check_git_boundary.py
```

`private-data/`と`sources/raw/`に加え、通常のPDF・XLS・XLSXが誤って別フォルダから追跡される場合も検出します。Gitで許可する文書fixtureは`tests/fixtures/fictional-`から始まる架空データだけです。

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

## Data Engine v0.6

3法人の取込は、共通の`SourceAdapter`契約と`AdapterRegistry`を経由します。

```text
SourceAdapter
  ├── NbfWorkbookSetAdapter
  ├── SingleWorkbookExcelAdapter (JRE)
  └── SingleWorkbookExcelAdapter (GLP)
        ↓
Workbook Layout検証
        ↓
法人別Parser
        ↓
Evidence付き共通JSON
        ↓
Import Run監査記録
```

各実行では次を`private-data/reports/`に保存します。

- `latest-import-run.json`：最新の実行結果
- `import-runs/run-*.json`：実行履歴、Adapterバージョン、入力SHA-256、件数、問題数
- `layout-baselines.json`：Excelシート構成の指紋と変更状態
- `all-import-report.json`：3法人の統合検証結果

同じ原本・同じAdapterバージョンからは同じ`idempotency_key`が生成されます。シート不足など互換性のないレイアウトは処理を止め、失敗記録を`private-data/quarantine/`へ保存します。レイアウト指紋はシート名・行列数・非空セル数だけから生成し、セル値を監査ログへ持ち出しません。

契約は次のファイルです。

- `scripts/data_engine/contracts.py`：SourceAdapter、ImportContext、AdapterResult
- `scripts/data_engine/registry.py`：Adapter登録と選択
- `scripts/data_engine/layout.py`：Workbookレイアウト検証
- `scripts/data_engine/runner.py`：Import Runと再現性管理
- `schema/import-run.schema.json`
- `schema/workbook-layout.schema.json`

## Data Quality Gate v0.7

3法人の統合後、`scripts/data_engine/quality.py`が次を決定論的に検査します。

- 物件IDの重複
- 物件名、投資法人、用途、住所等の必須項目
- CAP、稼働率等の数値範囲
- 数値ごとのEvidence（原本、取得日時、シート、セル、Parser情報）
- 座標の欠損・範囲
- 賃貸可能面積と賃貸面積の整合性

エラーがある場合、検査対象を`private-data/quarantine/`へ記録し、既存の正常な`properties.json`を上書きしません。合格・警告の場合だけ画面用データを更新します。詳細レポートは`private-data/reports/latest-quality-report.json`へ保存します。

画面上部の「品質」ボタンでは、投資法人別・指標別のEvidence充足率と品質Gateの結果を確認できます。画面用APIは集計値だけを返し、物件別問題、原本URL、ファイル名、SHA-256を返しません。契約は`schema/data-quality-report.schema.json`です。

現在の234物件では、1,561時点・15,707数値のEvidence充足率100%、座標充足率100%、品質Gateエラー0件を確認しています。公式Excelで利回りが0%と記録されている「該当なし」の値は、実在する0%利回りと誤認しないよう欠損値へ正規化します。

## Dataset Change Detection v0.8

品質Gateを通過したデータだけを前回の正常データと比較し、次を検出します。

- 新規物件と除外候補（除外だけで売却と断定しません）
- 物件名、住所、用途、座標等のマスター変更
- 新規・削除された決算期データ
- CAP、NOI、稼働率、鑑定評価額等の追加・削除・変更
- 数値が同じでも根拠資料が変わったEvidenceの再紐付け

詳細差分は`private-data/reports/latest-change-report.json`へ保存し、各数値変更に新しい出典document ID、取得日時、PDFページまたはExcelシート・セルを保持します。正常データは`private-data/snapshots/`へgzip圧縮し、同じ業務値・Evidenceの版は重複保存しません。

画面上部の「差分」ボタンは投資法人別・指標別の集計だけを表示します。物件名、物件ID、変更前後の数値、原本情報は画面用APIへ出さず、Mac内の詳細レポートに限定します。契約は`schema/dataset-change-report.schema.json`です。

## PDF Adapter基盤 v0.9

PDFはExcelと同じ`SourceAdapter`契約へ接続しますが、本文や表を監査ログ・Git・ブラウザへ出さない設計です。

```text
private-data/raw/*.pdf
        ↓
PDF構造検査（ページ数・寸法・文字量・表数・画像数）
        ↓
レイアウト指紋・OCR要否・互換性Gate
        ↓
投資法人別PDF Parser
        ↓
ページ番号 + bbox付きEvidence
        ↓
共通JSON・品質Gate・差分検出
```

実装済みの基盤は次の通りです。

- `scripts/data_engine/pdf.py`：PDF構造検査、本文のメモリ内抽出、文字位置検索
- `scripts/data_engine/pdf_adapters.py`：`private-data/raw`専用のPDF Adapter契約
- `scripts/inspect_pdf.py`：本文や数値を保存せずPDF互換性だけを確認するCLI
- `schema/pdf-layout.schema.json`：Privacy-safeなPDF構造Schema
- `evidence.pdf_locator`：1始まりのページ番号とPDF座標を持つEvidence
- OCRが必要な画像PDFと互換性のないレイアウトの処理停止

PDF機能の依存ライブラリはプロジェクト専用の仮想環境へ一度だけ導入します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-pdf.txt
```

以後、PDF処理を行うターミナルでは最初に`source .venv/bin/activate`を実行します。仮想環境は`.gitignore`対象で、GitHubへ登録されません。

検査するPDFはGitへ置かず、`private-data/raw/`へ保存します。例えば`private-data/raw/fictional-report.pdf`を検査する場合：

```bash
python3 scripts/inspect_pdf.py --file fictional-report.pdf
```

検査結果は`private-data/reports/pdf-inspections/`だけに保存されます。本文、表、物件名、CAP、NOI等は検査レポートへ含めません。

## NBF決算説明会資料 Adapter v0.10

第49期決算説明会資料から、ポートフォリオ賃貸収入・NOI・平均稼働率と、外部成長ページの取得・売却物件に関する価格・NOI利回りを抽出します。各値にはPDFページとbboxを持つEvidenceを付け、確認状態は`pending`とします。

```bash
source .venv/bin/activate
python3 scripts/import_nbf_pdf.py --accept-source-terms
```

原本は`private-data/raw/nbf-49-earnings-presentation.pdf`、正規化結果は`private-data/normalized/nbf-49-earnings-presentation.json`、値を含まない監査レポートは`private-data/reports/pdf-imports/`へ保存されます。既存の234物件Excelデータは上書きせず、補足データとして分離します。

公式PDFのレイアウトが変わった場合は互換性Gateで停止し、問題の詳細をローカルで確認してからAdapter定義を更新します。GitHubへ登録するのはAdapter、Schema、架空PDFテストだけです。

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

契約は`schema/source-evidence.schema.json`、`schema/canonical-property-period.schema.json`、`schema/metric-dictionary.json`です。Excel AdapterはExcelシート・セル、PDF Adapter基盤はPDFページとbboxまで記録します。実PDFの数値は資料別Adapterで決定論的に抽出し、confidenceと人手確認状態を保持します。

## テスト

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_git_boundary.py
```

同じ検証は`.github/workflows/ci.yml`でも実行され、Pull Requestと`main`更新時に、テスト、実データ境界、JavaScript/Python構文を自動確認します。CIには実データを渡さず、架空fixtureだけを使用します。
