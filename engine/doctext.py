"""보도자료 첨부 문서(PDF, 없으면 HWPX)에서 원문 글자를 뽑는다.

PDF: 위→아래 순서로 읽는다. 표(2줄×2칸 이상)는 본문 글로 풀지 않고(순서가 섞여 뜻이 달라짐)
그 자리에 "⟦표N⟧" 표시 줄을 넣고, 표의 칸 글자는 따로 돌려준다(카드에 표로 다시 그림).
담당부서·연락처 표는 버린다.
"""
from __future__ import annotations

import html
import io
import re
import zipfile

TABLE_MARK = "⟦표{n}⟧"
CONTACT_WORDS = ("담당 부서", "담당부서", "책임자", "담당자", "문의처", "연락처")


def _clean_cell(c) -> str:
    """칸 글자: 줄바꿈만 띄어쓰기로(글자는 그대로)."""
    return re.sub(r"\s*\n\s*", " ", c or "").strip()


def pdf_text(data: bytes, with_info: bool = False):
    import pymupdf

    doc = pymupdf.open(stream=data, filetype="pdf")
    out_pages: list[str] = []
    raw_pages: list[str] = []
    tables: list[list[list[str]]] = []
    tables_removed = 0
    for page in doc:
        raw_pages.append(page.get_text())
        boxes = []           # (Rect, 표 번호 또는 None=버림)
        try:
            for t in page.find_tables().tables:
                if t.row_count < 2 or t.col_count < 2:
                    continue
                rows = [[_clean_cell(c) for c in r] for r in t.extract()]
                flat = " ".join(" ".join(r) for r in rows)
                if any(w in flat for w in CONTACT_WORDS):
                    boxes.append((pymupdf.Rect(t.bbox), None))
                    tables_removed += 1
                    continue
                tables.append(rows)
                boxes.append((pymupdf.Rect(t.bbox), len(tables)))
        except Exception:
            pass
        rows = []
        placed: set[int] = set()
        d = page.get_text("dict")
        for block in d["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"])
                if not text.strip():
                    continue
                r = pymupdf.Rect(line["bbox"])
                center = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
                inside = [(b, n) for b, n in boxes if b.contains(center)]
                if inside:
                    b, n = inside[0]
                    if n and n not in placed:           # 표 자리에 표시 줄 하나
                        placed.add(n)
                        rows.append((round(b.y0, 0), b.x0, TABLE_MARK.format(n=n)))
                    continue
                rows.append((round(r.y0, 0), r.x0, text))
        for b, n in boxes:                              # 글줄이 하나도 안 걸린 표
            if n and n not in placed:
                rows.append((round(b.y0, 0), b.x0, TABLE_MARK.format(n=n)))
        rows.sort(key=lambda x: (x[0], x[1]))
        # 같은 높이(±2pt)에 나뉜 조각은 한 줄로(표시 줄은 따로)
        merged: list[list] = []
        for y, x, text in rows:
            if merged and abs(merged[-1][0] - y) <= 2 and "⟦표" not in text and "⟦표" not in merged[-1][2]:
                merged[-1][2] += text
            else:
                merged.append([y, x, text])
        out_pages.append("\n".join(m[2] for m in merged))
    doc.close()
    text = "\n".join(out_pages)
    info = {"tables_removed": tables_removed, "tables": tables, "raw_text": "\n".join(raw_pages)}
    return (text, info) if with_info else text


def hwpx_text(data: bytes, with_info: bool = False):
    """HWPX = zip 안의 XML. 문단(<hp:p>)마다 줄바꿈. 표(<hp:tbl>) 안의 글은 뺀다."""
    out: list[str] = []
    tables = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
        for n in names:
            xml = z.read(n).decode("utf-8", "replace")
            tables += len(re.findall(r"<hp:tbl\b", xml))
            xml = re.sub(r"<hp:tbl\b.*?</hp:tbl>", "", xml, flags=re.S)
            for para in re.findall(r"<hp:p\b.*?</hp:p>", xml, flags=re.S):
                texts = re.findall(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", para, flags=re.S)
                line = "".join(re.sub(r"<[^>]+>", "", t) for t in texts)
                out.append(html.unescape(line))
    text = "\n".join(out)
    return (text, {"tables_removed": tables, "tables": [], "raw_text": text}) if with_info else text
