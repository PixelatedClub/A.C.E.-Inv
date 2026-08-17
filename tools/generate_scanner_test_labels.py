from __future__ import annotations

from pathlib import Path

from inventory_app.barcode_utils import write_direct_label_pdf


TEST_RECORDS = [
    {
        "barcode_id": "A0000001",
        "item_name": "Soft Blues Rank",
        "category": "Insignia",
        "variant": "GMC 100 (C/4C)",
        "item_type": "Soft Blues Ranks",
        "total_quantity": 12,
    },
    {
        "barcode_id": "A0000042",
        "item_name": "Hard Blues Rank",
        "category": "Insignia",
        "variant": "C/Capt",
        "item_type": "Hard Blues Ranks",
        "total_quantity": 2,
    },
    {
        "barcode_id": "A0012345",
        "item_name": "OCP Rank Patch",
        "category": "Insignia",
        "variant": "C/Lt Col",
        "item_type": "OCP Rank Patches",
        "total_quantity": 4,
    },
    {
        "barcode_id": "A9999999",
        "item_name": "OCP Rank Patch",
        "category": "Insignia",
        "variant": "C/Col",
        "item_type": "OCP Rank Patches",
        "total_quantity": 1,
    },
]


def main() -> None:
    repository_root = Path(__file__).resolve().parent.parent
    destination = repository_root / "docs" / "A.C.E_Tera_Scanner_Test_Labels.pdf"
    write_direct_label_pdf(
        destination,
        TEST_RECORDS,
        "A.C.E.",
        title="A.C.E. Tera Scanner Test Labels - Exact 2 x 1 Inch",
    )
    print(destination)


if __name__ == "__main__":
    main()
