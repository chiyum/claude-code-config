#!/usr/bin/env python3
"""verify-external-spec.py — 外部凍結規格（SPEC.md + manifest.json）的確定性驗證器

外部規格模式（見 ~/.claude/acceptance/EXTERNAL_SPEC_PROTOCOL.md）的入口 gate 與每個 gate 的漂移檢查。
只讀檔、算 hash、比對欄位；不執行 SPEC 內任何內容，不信任 front matter 字串，不用 eval。

用法：
  python3 verify-external-spec.py --spec /abs/path/SPEC.md                 # 開發入口：必須 FROZEN
  python3 verify-external-spec.py --spec ... --expected-sha256 <state hash>  # gate 漂移檢查
  python3 verify-external-spec.py --spec ... --mode check                    # /spec-check：允許 DRAFT
  python3 verify-external-spec.py --spec ... --expected-product example_product    # 與已載入產品比對
  python3 verify-external-spec.py --spec ... --confirm-environment prod      # 使用者已確認 prod 後才加

輸出：
  stdout 一律是一個 JSON 物件。成功時 ok=true 並帶正規化 metadata（可直接 jq 合進 state）；
  失敗時 ok=false、error=<錯誤類型>、message、details。stderr 另印一行人讀摘要「<錯誤類型>: <訊息>」。

錯誤類型與 exit code：
  0  OK
  2  SPEC_NOT_FOUND                      4  SPEC_INVALID           6  SPEC_SUPERSEDED
  3  MANIFEST_NOT_FOUND                  5  SPEC_NOT_FROZEN        7  SPEC_DRIFT
  8  PRODUCT_MISMATCH                    9  ENVIRONMENT_REQUIRES_CONFIRMATION
  64 用法錯誤
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

EXIT_CODES = {
    "SPEC_NOT_FOUND": 2,
    "MANIFEST_NOT_FOUND": 3,
    "SPEC_INVALID": 4,
    "SPEC_NOT_FROZEN": 5,
    "SPEC_SUPERSEDED": 6,
    "SPEC_DRIFT": 7,
    "PRODUCT_MISMATCH": 8,
    "ENVIRONMENT_REQUIRES_CONFIRMATION": 9,
}

# SPEC front matter 與 manifest 必須一致的欄位（status 在 SUPERSEDED 情境另有處理）
CONSISTENT_FIELDS = ("spec_id", "product", "version", "status", "target_environment")
MANIFEST_REQUIRED = (
    "spec_id", "product", "version", "status", "approved_by", "frozen_at",
    "target_environment", "risk_level", "spec_sha256", "supersedes",
)
FRONT_MATTER_REQUIRED = (
    "spec_id", "product", "version", "status", "approved_by", "target_environment", "risk_level",
)
VALID_STATUS = ("DRAFT", "FROZEN", "SUPERSEDED")
PROD_ENV_NAMES = ("prod", "production")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
AC_HEADING_RE = re.compile(r"^### (A[0-9]+)(?:\s|$)")
# 「未決問題」章節內視為「無」的寫法
EMPTY_MARKERS = {"無", "無。", "（無）", "(無)", "none", "n/a", "-", "- 無", "* 無", "無未決問題"}


class SpecError(Exception):
    def __init__(self, error, message, **details):
        super().__init__(message)
        self.error = error
        self.message = message
        self.details = details


def now_iso():
    """帶時區的 ISO 8601（本機時區）。"""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def norm(v):
    """欄位比對前的正規化：轉字串、去頭尾空白；None 維持 None。"""
    if v is None:
        return None
    return str(v).strip()


def read_spec_bytes(path):
    if not os.path.isfile(path):
        raise SpecError("SPEC_NOT_FOUND", f"找不到 SPEC 檔：{path}", spec_path=path)
    with open(path, "rb") as f:
        return f.read()


def decode_spec(raw, path):
    """UTF-8、無 BOM、LF；違反任一項即 SPEC_INVALID。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        raise SpecError("SPEC_INVALID", "SPEC 含 UTF-8 BOM；規約要求無 BOM", spec_path=path)
    if b"\r\n" in raw:
        raise SpecError("SPEC_INVALID", "SPEC 含 CRLF 換行；規約要求 LF", spec_path=path)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SpecError("SPEC_INVALID", f"SPEC 不是合法 UTF-8：{e}", spec_path=path)


def parse_front_matter(text, path):
    """解析最上方 --- 包起來的 key: value 區塊（YAML 子集，不做任何求值）。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise SpecError("SPEC_INVALID", "SPEC 第一行必須是 front matter 起始符 ---", spec_path=path)
    fm = {}
    end = None
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            end = i
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise SpecError("SPEC_INVALID", f"front matter 第 {i + 1} 行不是 key: value 形式：{line!r}", spec_path=path)
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # 去掉成對引號；不解析任何其他 YAML 語法
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            raise SpecError("SPEC_INVALID", f"front matter 欄位名不合法：{key!r}", spec_path=path)
        fm[key] = value
    if end is None:
        raise SpecError("SPEC_INVALID", "front matter 沒有結尾 ---", spec_path=path)
    body = "\n".join(lines[end + 1:])
    return fm, body


def load_manifest(spec_path):
    manifest_path = os.path.join(os.path.dirname(spec_path), "manifest.json")
    if not os.path.isfile(manifest_path):
        raise SpecError("MANIFEST_NOT_FOUND", f"SPEC 同目錄缺 manifest.json：{manifest_path}",
                        spec_path=spec_path, manifest_path=manifest_path)
    try:
        with open(manifest_path, "rb") as f:
            raw = f.read()
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SpecError("SPEC_INVALID", f"manifest.json 不是合法 UTF-8 JSON：{e}", manifest_path=manifest_path)
    if not isinstance(data, dict):
        raise SpecError("SPEC_INVALID", "manifest.json 頂層必須是 JSON 物件", manifest_path=manifest_path)
    missing = [k for k in MANIFEST_REQUIRED if k not in data]
    if missing:
        raise SpecError("SPEC_INVALID", f"manifest.json 缺欄位：{', '.join(missing)}",
                        manifest_path=manifest_path, missing=missing)
    for k in MANIFEST_REQUIRED:
        v = data[k]
        if k == "supersedes":
            if v is not None and not isinstance(v, str):
                raise SpecError("SPEC_INVALID", "manifest.supersedes 必須是 null 或字串", manifest_path=manifest_path)
            continue
        if not isinstance(v, (str, int, float)) or isinstance(v, bool) or norm(v) == "":
            raise SpecError("SPEC_INVALID", f"manifest.{k} 必須是非空字串", manifest_path=manifest_path, field=k)
    return manifest_path, data


def section_body(body, title_keyword):
    """取出標題含關鍵字的 ## 章節內文（到下一個 ## 為止）；找不到回 None。"""
    lines = body.split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^##\s", line) and title_keyword in line:
            start = i + 1
            break
    if start is None:
        return None
    out = []
    for line in lines[start:]:
        if re.match(r"^##\s", line):
            break
        out.append(line)
    return "\n".join(out)


def acceptance_ids(body, path):
    """收集 ### A<n> 標題；重複即 SPEC_INVALID；回傳依出現順序的 id 清單。"""
    ids, seen, dups = [], set(), []
    for line in body.split("\n"):
        m = AC_HEADING_RE.match(line)
        if not m:
            continue
        aid = m.group(1)
        if aid in seen:
            dups.append(aid)
        seen.add(aid)
        ids.append(aid)
    if dups:
        raise SpecError("SPEC_INVALID", f"驗收條件編號重複：{', '.join(sorted(set(dups)))}", spec_path=path, duplicates=sorted(set(dups)))
    if not ids:
        raise SpecError("SPEC_INVALID", "SPEC 內找不到任何「### A<n>」驗收條件", spec_path=path)
    return ids


def open_questions_is_empty(body):
    """FROZEN 時「未決問題」章節必須為無 / 空集合。章節不存在視為空。"""
    sec = section_body(body, "未決問題")
    if sec is None:
        return True, []
    leftovers = []
    for line in sec.split("\n"):
        s = line.strip()
        if not s or s.startswith("<!--"):
            continue
        s_norm = s.lstrip("-*").strip().rstrip("。").lower()
        if s_norm in EMPTY_MARKERS or s.lower() in EMPTY_MARKERS:
            continue
        leftovers.append(s)
    return (len(leftovers) == 0), leftovers


def parse_iso_tz(value):
    """帶時區的 ISO 8601；裸時間或格式錯誤回 None。"""
    try:
        d = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo is not None else None


def verify(args):
    warnings = []
    spec_path = os.path.realpath(os.path.expanduser(args.spec))
    raw = read_spec_bytes(spec_path)
    text = decode_spec(raw, spec_path)
    fm, body = parse_front_matter(text, spec_path)

    missing = [k for k in FRONT_MATTER_REQUIRED if not norm(fm.get(k))]
    if missing:
        raise SpecError("SPEC_INVALID", f"SPEC front matter 缺欄位：{', '.join(missing)}", spec_path=spec_path, missing=missing)

    manifest_path, manifest = load_manifest(spec_path)
    actual_sha = hashlib.sha256(raw).hexdigest()

    spec_status = norm(fm["status"]).upper()
    manifest_status = norm(manifest["status"]).upper()
    for label, st in (("SPEC", spec_status), ("manifest", manifest_status)):
        if st not in VALID_STATUS:
            raise SpecError("SPEC_INVALID", f"{label} status 不合法：{st!r}（允許 DRAFT / FROZEN / SUPERSEDED）", spec_path=spec_path)

    # 取代狀態只在 manifest 標記（改 SPEC 本體會動到 hash），所以先判 manifest
    if manifest_status == "SUPERSEDED":
        raise SpecError(
            "SPEC_SUPERSEDED",
            f"此版本已被取代（manifest status=SUPERSEDED），不得作為新任務來源；請向規格治理者取得最新版本路徑，不要自行猜測",
            spec_path=spec_path, manifest_path=manifest_path,
            spec_id=norm(manifest.get("spec_id")), version=norm(manifest.get("version")),
        )

    # metadata 一致性
    mismatches = {}
    for k in CONSISTENT_FIELDS:
        a, b = norm(fm.get(k)), norm(manifest.get(k))
        if k == "status":
            a, b = spec_status, manifest_status
        if a != b:
            mismatches[k] = {"spec": a, "manifest": b}
    if mismatches:
        raise SpecError("SPEC_INVALID", f"SPEC 與 manifest 欄位不一致：{', '.join(mismatches)}",
                        spec_path=spec_path, manifest_path=manifest_path, mismatches=mismatches)

    # hash：manifest 記錄的必須等於實際 bytes
    manifest_sha = norm(manifest["spec_sha256"]).lower()
    if not SHA256_RE.match(manifest_sha):
        raise SpecError("SPEC_INVALID", "manifest.spec_sha256 不是 64 位十六進位 SHA-256", manifest_path=manifest_path)
    if manifest_sha != actual_sha:
        raise SpecError("SPEC_DRIFT", "SPEC 實際內容的 SHA-256 與 manifest 記錄不符（SPEC 在凍結後被改動，或 manifest 未重算）",
                        spec_path=spec_path, manifest_path=manifest_path,
                        manifest_sha256=manifest_sha, actual_sha256=actual_sha)
    if args.expected_sha256:
        exp = norm(args.expected_sha256).lower()
        if exp != actual_sha:
            raise SpecError("SPEC_DRIFT", "SPEC 目前的 SHA-256 與 run 綁定的 hash 不符（規格漂移）",
                            spec_path=spec_path, expected_sha256=exp, actual_sha256=actual_sha)

    if manifest_sha in body:
        warnings.append("SPEC 本體出現自己的 hash 字串；規約要求不要把 hash 寫進 SPEC")

    # 狀態 gate
    status = spec_status
    if status == "DRAFT" and args.mode == "dev":
        raise SpecError("SPEC_NOT_FROZEN", "SPEC 狀態為 DRAFT，禁止進入開發；只允許 /spec-check 做可行性檢查",
                        spec_path=spec_path, status=status)

    # 結構檢查
    ids = acceptance_ids(body, spec_path)
    nums = [int(i[1:]) for i in ids]
    if nums != list(range(1, len(nums) + 1)):
        warnings.append(f"驗收條件編號非 A1 起連號：{', '.join(ids)}")

    if status == "FROZEN":
        empty, leftovers = open_questions_is_empty(body)
        if not empty:
            raise SpecError("SPEC_INVALID", "FROZEN 狀態的 SPEC 其「未決問題」章節必須為無 / 空集合",
                            spec_path=spec_path, open_questions=leftovers[:10])
        if parse_iso_tz(manifest.get("frozen_at")) is None:
            raise SpecError("SPEC_INVALID", f"manifest.frozen_at 必須是帶時區的 ISO 8601：{manifest.get('frozen_at')!r}",
                            manifest_path=manifest_path)

    # 版本目錄慣例（僅警告，不阻擋 fixture 放在其他位置）
    parent = os.path.basename(os.path.dirname(spec_path))
    version = norm(fm["version"])
    if parent != f"v{version}":
        warnings.append(f"SPEC 所在目錄 {parent!r} 與慣例 v{version} 不同")

    # 產品比對
    product = norm(fm["product"])
    if args.expected_product and norm(args.expected_product) != product:
        raise SpecError("PRODUCT_MISMATCH", f"SPEC product={product!r} 與目前載入的產品 {norm(args.expected_product)!r} 不同",
                        spec_product=product, loaded_product=norm(args.expected_product))
    if not args.skip_product_registry:
        pfile = os.path.join(os.path.expanduser(args.products_dir), f"{product}.md")
        if not os.path.isfile(pfile):
            raise SpecError("PRODUCT_MISMATCH", f"SPEC product={product!r} 未在產品配置目錄註冊（缺 {pfile}）",
                            spec_product=product, products_dir=args.products_dir)

    # 環境
    env = norm(fm["target_environment"]).lower()
    if env in PROD_ENV_NAMES and norm(args.confirm_environment or "").lower() != env:
        raise SpecError("ENVIRONMENT_REQUIRES_CONFIRMATION",
                        f"target_environment={env!r} 命中必問白名單（碰 prod）：必須先取得使用者明確確認，再以 --confirm-environment {env} 重跑",
                        target_environment=env)

    supersedes = manifest.get("supersedes")
    if supersedes:
        # 舊版若存在且尚未標 SUPERSEDED，只提醒治理者，不阻擋
        old_manifest = os.path.join(os.path.dirname(os.path.dirname(spec_path)), f"v{supersedes}", "manifest.json")
        if os.path.isfile(old_manifest):
            try:
                with open(old_manifest, "rb") as f:
                    old_status = norm(json.loads(f.read().decode("utf-8")).get("status"))
                if (old_status or "").upper() != "SUPERSEDED":
                    warnings.append(f"本版宣稱取代 v{supersedes}，但該版 manifest status={old_status!r} 尚未標 SUPERSEDED")
            except (OSError, ValueError, UnicodeDecodeError):
                warnings.append(f"無法讀取被取代版本的 manifest：{old_manifest}")

    result = {
        "ok": True,
        "mode": args.mode,
        "checked_at": now_iso(),
        "spec_id": norm(fm["spec_id"]),
        "product": product,
        "spec_version": version,
        "status": status,
        "approved_by": norm(fm["approved_by"]),
        "target_environment": env,
        "risk_level": norm(fm["risk_level"]),
        "frozen_at": norm(manifest.get("frozen_at")),
        "supersedes": supersedes,
        "spec_path": spec_path,
        "manifest_path": manifest_path,
        "spec_sha256": actual_sha,
        "acceptance_ids": ids,
        "acceptance_count": len(ids),
        "warnings": warnings,
    }
    if args.mode == "check" and status == "FROZEN":
        result["frozen_audit"] = True
        result["notice"] = "此 SPEC 已 FROZEN：本次為凍結後稽核，只能回報發現，不得修改 SPEC"
    return result


def main():
    ap = argparse.ArgumentParser(description="外部凍結規格驗證器（只讀）")
    ap.add_argument("--spec", required=True, help="SPEC.md 路徑（建議絕對路徑）")
    ap.add_argument("--mode", choices=("dev", "check"), default="dev",
                    help="dev=開發入口 / gate（必須 FROZEN）；check=/spec-check（允許 DRAFT）")
    ap.add_argument("--expected-sha256", default="", help="state 中綁定的 hash；不符即 SPEC_DRIFT")
    ap.add_argument("--expected-product", default="", help="目前載入的產品代號；不符即 PRODUCT_MISMATCH")
    ap.add_argument("--products-dir", default=os.path.join(os.path.expanduser("~"), ".claude", "products"),
                    help="產品配置目錄（預設 ~/.claude/products）")
    ap.add_argument("--skip-product-registry", action="store_true", help="不檢查 product 是否已註冊（測試 fixture 用）")
    ap.add_argument("--confirm-environment", default="",
                    help="使用者已明確確認的環境名（如 prod）；只有拿到確認才加此參數")
    try:
        args = ap.parse_args()
    except SystemExit:
        sys.exit(64)

    try:
        result = verify(args)
    except SpecError as e:
        out = {"ok": False, "error": e.error, "message": e.message, "details": e.details, "checked_at": now_iso()}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"{e.error}: {e.message}", file=sys.stderr)
        sys.exit(EXIT_CODES[e.error])

    print(json.dumps(result, ensure_ascii=False, indent=2))
    for w in result["warnings"]:
        print(f"[warn] {w}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
