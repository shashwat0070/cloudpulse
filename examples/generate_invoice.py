from pathlib import Path

content = b"""BT
/F1 16 Tf
50 750 Td
(SYNTHETIC INVOICE - NOT A REAL TRANSACTION) Tj
0 -40 Td
(Invoice: CP-001) Tj
0 -30 Td
(Vendor: Example Supplies) Tj
0 -30 Td
(Date: 2026-11-16) Tj
0 -30 Td
(Total: USD 125.00) Tj
ET
"""

objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    (
        b"<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> "
        b"/Contents 5 0 R >>"
    ),
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    (
        f"<< /Length {len(content)} >>\nstream\n".encode()
        + content
        + b"endstream"
    ),
]

pdf = bytearray(b"%PDF-1.4\n")
offsets = []

for number, obj in enumerate(objects, start=1):
    offsets.append(len(pdf))
    pdf.extend(f"{number} 0 obj\n".encode())
    pdf.extend(obj + b"\nendobj\n")

xref_position = len(pdf)
pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
pdf.extend(b"0000000000 65535 f \n")

for offset in offsets:
    pdf.extend(f"{offset:010d} 00000 n \n".encode())

pdf.extend(
    (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()
)

destination = Path(__file__).parent / "invoice.pdf"
destination.write_bytes(pdf)
print(f"Created {destination}")