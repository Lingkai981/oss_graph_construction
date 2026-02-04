#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
from pathlib import Path

# XML 1.0 非法控制字符（保留 \t \n \r）
ILLEGAL_XML_10_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

# 替换“裸 &”（不是合法 entity 的那些）
BARE_AMP_RE = re.compile(r"&(?!(amp|lt|gt|quot|apos);|#\d+;|#x[0-9A-Fa-f]+;)")

def clean_graphml_text(text: str) -> tuple[str, int, int]:
    """返回：清洗后的文本、删除控制字符数、替换裸&数"""
    before = text
    text2 = ILLEGAL_XML_10_RE.sub("", text)
    removed_ctrl = len(before) - len(text2)

    # 统计替换次数（finditer 计数）
    amp_count = sum(1 for _ in BARE_AMP_RE.finditer(text2))
    text3 = BARE_AMP_RE.sub("&amp;", text2)

    return text3, removed_ctrl, amp_count

def process_file(p: Path, *, in_place: bool, make_backup: bool) -> tuple[bool, str]:
    raw = p.read_bytes()

    # 尽量按 utf-8 解；无法解就用 replace（至少让文件变成“可解析的 utf-8 文本”）
    text = raw.decode("utf-8", errors="replace")

    cleaned, removed_ctrl, amp_fixed = clean_graphml_text(text)
    changed = (cleaned != text)

    if not changed:
        return False, "no_change"

    if in_place:
        if make_backup:
            backup = p.with_suffix(p.suffix + ".bak")
            if not backup.exists():
                backup.write_bytes(raw)
        p.write_text(cleaned, encoding="utf-8", newline="\n")

    return True, f"ctrl_removed={removed_ctrl}, amp_fixed={amp_fixed}"

def main():
    ap = argparse.ArgumentParser(description="Clean invalid XML chars in GraphML files")
    ap.add_argument("--root", type=str, default="output/monthly-graphs", help="GraphML 根目录")
    ap.add_argument("--glob", type=str, default="**/*.graphml", help="匹配模式")
    ap.add_argument("--in-place", action="store_true", help="原地写回（否则只做 dry-run 统计）")
    ap.add_argument("--no-backup", action="store_true", help="不生成 .bak 备份")
    args = ap.parse_args()

    root = Path(args.root)
    files = sorted(root.glob(args.glob))

    if not files:
        print(f"[WARN] No files matched under {root} with pattern {args.glob}")
        return

    total = 0
    changed_n = 0
    for p in files:
        total += 1
        changed, info = process_file(
            p,
            in_place=args.in_place,
            make_backup=not args.no_backup,
        )
        if changed:
            changed_n += 1
            mode = "FIXED" if args.in_place else "WOULD_FIX"
            print(f"[{mode}] {p} :: {info}")

    print(f"\nDone. total={total}, changed={changed_n}, in_place={args.in_place}")

if __name__ == "__main__":
    main()
