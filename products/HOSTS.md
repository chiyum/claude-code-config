# 遠端主機登記表（SSH／Tailscale 連線方式唯一來源）

用途：使用者提到主機別名、IP 或「連到某台電腦」時，主 Claude 先讀本表決定怎麼連。密碼與 token 一律不寫這裡，只指向 `~/.claude/SECRETS.local.md` 的章節。別名定義在本機 `~/.ssh/config`；本表與它不一致時以 `ssh -G <別名>` 實測為準並回填本表。

## 連線通則

- 區網主機只有本機在同一區網時才連得到；`Tailscale IP` 欄有值的主機在任何網路都能連
- SSH 進 Windows 下 PowerShell 時引號會被兩層 shell 吃掉，改用 `powershell -NoProfile -EncodedCommand <UTF-16LE base64>`

## 主機清單

| 別名 | 用途／所屬產品 | 區網 IP:port | Tailscale IP | 帳號 | 金鑰／密碼 | OS／硬體 | 最後驗證 |
|---|---|---|---|---|---|---|---|
| `example-host` | `example_product` 的 dev 主機（Docker stack） | `<區網 IP>:22` | `<Tailscale IP>`（無則填「無」） | `deploy` | `~/.ssh/id_ed25519_example`；sudo 密碼見 SECRETS「example-host」 | Ubuntu 24.04 | YYYY-MM-DD |
