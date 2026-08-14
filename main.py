from inventory_app import InventoryApp, load_settings


def main() -> None:
    app = InventoryApp(load_settings())
    app.mainloop()


if __name__ == "__main__":
    main()
