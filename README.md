# J-REIT Intelligence v0.2

Property Intelligence Platform（PIP）の最初のモジュールです。地図、検索、物件詳細、出典セル表示、CSV出力を備えます。

## データ方針

- 公開GitHubにはプログラムと架空データだけを置きます。
- NBF公式Excelの原本と変換後データはMac内だけに保存し、Git管理から除外します。
- 公式ファイルの「ご利用上の注意」と利用規約を確認し、許可のない再配布・転載を行わないでください。
- 数値は投資・融資判断に使用する前に原資料と照合してください。

## NBF実データのローカル取込

```bash
python3 scripts/import_nbf.py --accept-source-terms
```

原本を更新する場合：

```bash
python3 scripts/import_nbf.py --accept-source-terms --refresh
```

生成物は `data/properties.json` と `data/import-report.json` です。住所座標は国土地理院AddressSearchによる自動候補であり、建物位置の確認済み座標ではありません。

## ローカル起動

```bash
python3 -m http.server 8000
```

ブラウザで <http://localhost:8000> を開きます。終了は `Control + C` です。

`data/properties.json` が存在しない場合は、架空データへ自動的に切り替わります。地図タイルとLeafletの表示にはネット接続が必要です。
