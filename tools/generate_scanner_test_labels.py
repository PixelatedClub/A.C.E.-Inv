from __future__ import annotations

from pathlib import Path

from inventory_app.barcode_utils import LABEL_COLUMNS, LABEL_ROWS, write_label_pdf


TEST_RECORDS = [
    {
        "barcode_id": f"A{position:07d}",
        "item_name": (
            f"PLS892 Test R{((position - 1) // LABEL_COLUMNS) + 1}"
            f"C{((position - 1) % LABEL_COLUMNS) + 1}"
        ),
        "category": "Scanner Test",
        "variant": "2 x 1",
        "item_type": "PLS892",
        "total_quantity": 1,
    }
    for position in range(1, (LABEL_COLUMNS * LABEL_ROWS) + 1)
]


def main() -> None:
    repository_root = Path(__file__).resolve().parent.parent
    destination = repository_root / "docs" / "A.C.E_Tera_Scanner_Test_Labels.pdf"
    write_label_pdf(
        destination,
        TEST_RECORDS,
        "A.C.E.",
        title="A.C.E. PLS892 Scanner Test Sheet - 40 Labels",
    )
    print(destination)


if __name__ == "__main__":
    main()
