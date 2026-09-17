"""보도자료 첨부 문서(PDF, 없으면 HWPX)에서 원문 글자를 뽑는다.

PDF: 위→아래 순서로 읽고, 표(2줄×2칸 이상) 안의 글은 뺀다(표를 글로 풀면 순서가 섞여 뜻이 달라짐).
뺀 표 개수는 돌려줘서 확인 페이지에 알린다.
"""
from __future__ import annotations

import html
import io
import re
import zipfile


def pdf_text(data: bytes, with_info: bool = False):
    import pymupdf

    doc = pymupdf.open(stream=data, filetype="pdf")
    out_pages: list[str] = []
    tables_removed = 0
    for page in doc:
        boxes = []
        try:
            for t in page.find_tables().tables:
                if t.row_count >= 2 and t.col_count >= 2:
                    boxes.append(pymupdf.Rect(t.bbox))
        except Exception:
            pass
        tables_removed += len(boxes)
        rows = []
        d = page.get_text("dict")
        for block in d["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"])
                if not text.strip():
                    continue
                r = pymupdf.Rect(line["bbox"])
                center = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
                if any(b.contains(center) for b in boxes):
                    continue
                rows.append((round(r.y0, 0), r.x0, text))
        rows.sort(key=lambda x: (x[0], x[1]))
        # 같은 높이(±2pt)에 나뉜 조각은 한 줄로
        merged: list[list] = []
        for y, x, text in rows:
            if merged and abs(merged[-1][0] - y) <= 2:
                merged[-1][2] += text
            else:
                merged.append([y, x, text])
        out_pages.append("\n".join(m[2] for m in merged))
    doc.close()
    text = "\n".join(out_pages)
    return (text, {"tables_removed": tables_removed}) if with_info else text


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
    return (text, {"tables_removed": tables}) if with_info else text
