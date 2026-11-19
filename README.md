# SVリーグ女子 全チームスタメン

大同生命SV.LEAGUE WOMEN 2026-27 全14チームの、セット別スタメン（コート図）を見られる単一HTMLページです。
データは公式サイトの公式帳票（帳票B／A）から自動取得しています。

## 構成
| ファイル | 役割 |
|---|---|
| `data/starters.json` | 正データ（公式から取得） |
| `scripts/fetch_starters.py` | 取得・解析・検証。`--update` が週次更新の本体 |
| `scripts/verify.py` | オフライン検証（先発6人、セット数、検証例 試合37495） |
| `template.html` / `build.py` | 表示テンプレートとビルド。`index.html` を生成 |
| `.github/workflows/weekly-update.yml` | 毎週月曜 8:00 JST に自動更新 |

## 週次自動更新の流れ
1. `fetch_starters.py --update` … 延期試合の実施有無を再確認し、実施済みの新規試合を取り込む（未実施が30ID連続したら打ち切り）。
2. `verify.py` … 先発が6人ちょうど／セット数一致／検証例が崩れていないか。**1つでも失敗したらコミットせず終了**（Actions が失敗として通知）。
3. `build.py` → `index.html` 再生成 → 変更があれば commit & push → GitHub Pages が更新。

手動実行は Actions タブの weekly-update → Run workflow。ローカルでも同じコマンドで再現できます。
